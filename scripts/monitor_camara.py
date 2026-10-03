#!/usr/bin/env python3
"""Monitor de proposições penais na Câmara dos Deputados.

Baixa os arquivos anuais de dados abertos da Câmara (proposições, temas e autores),
seleciona as proposições de natureza penal (tema "Direito Penal e Processual Penal"
ou palavras-chave na ementa) e grava data/monitor/camara.json para a página do site.

Fonte: https://dadosabertos.camara.leg.br (arquivos atualizados diariamente).
Uso: python3 scripts/monitor_camara.py   (variável ANOS opcional, ex.: ANOS=2025,2026)
"""
import io, json, os, re, sys, time, urllib.request, csv
from datetime import datetime, timezone, timedelta

BASE = "https://dadosabertos.camara.leg.br/arquivos"
TIPOS = {"PL", "PLP", "PEC"}
HOJE = datetime.now(timezone(timedelta(hours=-3)))
ANOS = [int(a) for a in os.environ.get("ANOS", ",".join(str(y) for y in range(2023, HOJE.year + 1))).split(",")]
SAIDA = os.path.join(os.path.dirname(__file__), "..", "data", "monitor", "camara.json")


def baixar(url, tentativas=4):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "monitor-penal (site academico)", "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            print(f"  falha ({i+1}/{tentativas}) em {url}: {e}", file=sys.stderr)
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"não foi possível baixar {url}")


def ler_csv(url):
    bruto = baixar(url).decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(bruto), delimiter=";"))


def g(d, *chaves):
    for c in chaves:
        if c in d and d[c] not in (None, ""):
            return d[c]
    return ""


# Palavras-chave de natureza penal na ementa
PENAL = re.compile(
    r"c[óo]digo penal|decreto-lei n[ºo°.]*\s*2\.848|c[óo]digo de processo penal|decreto-lei n[ºo°.]*\s*3\.689|"
    r"execu[çc][ãa]o penal|lei n[ºo°.]*\s*7\.210|lei n[ºo°.]*\s*11\.343|crimes? hediondos?|lei n[ºo°.]*\s*8\.072|"
    r"lei n[ºo°.]*\s*9\.099|lei n[ºo°.]*\s*12\.850|organiza[çc][ãa]o criminosa|lavagem de (dinheiro|bens)|"
    r"\btipifica|\bcriminaliza|\bdescriminaliza|\bcrimes?\b|\bpenas?\b|\bcontraven[çc]|\bpris[ãa]o\b|\bpenal\b",
    re.I,
)
DIPLOMAS = [
    ("Código Penal", r"c[óo]digo penal(?! militar)|decreto-lei n[ºo°.]*\s*2\.848"),
    ("Código de Processo Penal", r"c[óo]digo de processo penal(?! militar)|decreto-lei n[ºo°.]*\s*3\.689"),
    ("Lei de Execução Penal", r"execu[çc][ãa]o penal|lei n[ºo°.]*\s*7\.210"),
    ("Lei de Drogas", r"lei n[ºo°.]*\s*11\.343|\bdrogas\b|entorpecente"),
    ("Crimes hediondos", r"hediond|lei n[ºo°.]*\s*8\.072"),
    ("Juizados Especiais (Lei 9.099)", r"lei n[ºo°.]*\s*9\.099"),
    ("Maria da Penha", r"maria da penha|lei n[ºo°.]*\s*11\.340"),
    ("Estatuto do Desarmamento", r"desarmamento|lei n[ºo°.]*\s*10\.826"),
    ("Organizações criminosas", r"lei n[ºo°.]*\s*12\.850|organiza[çc][ãa]o criminosa|fac[çc][ãa]o criminosa|mil[íi]cia"),
    ("Lavagem de dinheiro", r"lei n[ºo°.]*\s*9\.613|lavagem de"),
    ("ECA (crimes)", r"(estatuto da crian[çc]a|lei n[ºo°.]*\s*8\.069).{0,200}(crime|pena)|(crime|pena).{0,200}(estatuto da crian[çc]a|lei n[ºo°.]*\s*8\.069)"),
    ("Código de Trânsito (crimes)", r"(tr[âa]nsito|lei n[ºo°.]*\s*9\.503).{0,200}(crime|pena)|(crime|pena).{0,200}(tr[âa]nsito|lei n[ºo°.]*\s*9\.503)"),
    ("Penal Militar", r"penal militar|processo penal militar|decreto-lei n[ºo°.]*\s*1\.00[12]"),
]
NATUREZA = [
    ("Aumenta pena", r"aument\w* (a |as )?pena|agrav\w* (a |as )?pena|majora\w*|causa de aumento|qualificadora|eleva (a |as )?pena"),
    ("Cria ou altera tipo penal", r"tipifica|criminaliza|cria (o |um )?(novo )?(tipo|crime)|define (o |como )?crime|institui (o )?crime|novo tipo penal|prev[êe] (o )?crime"),
    ("Hediondez", r"hediond"),
    ("Processo penal", r"processo penal|inqu[ée]rito|pris[ãa]o preventiva|pris[ãa]o tempor[áa]ria|audi[êe]ncia de cust[óo]dia|fian[çc]a|acordo de n[ãa]o persecu"),
    ("Execução penal", r"execu[çc][ãa]o penal|progress[ãa]o de regime|livramento condicional|sa[íi]da tempor[áa]ria|regime (inicial|fechado|semiaberto)|remi[çc][ãa]o"),
    ("Reduz ou descriminaliza", r"descriminaliza|abolitio|reduz\w* (a |as )?pena|revoga (o |os )?(crime|tipo|art)"),
]
DIPLOMAS = [(n, re.compile(p, re.I | re.S)) for n, p in DIPLOMAS]
NATUREZA = [(n, re.compile(p, re.I | re.S)) for n, p in NATUREZA]
ENCERRADA = re.compile(r"arquivad|transformad|retirad|prejudicad|vetad|devolvid", re.I)


def main():
    itens, analisadas = {}, 0
    for ano in ANOS:
        print(f"Ano {ano}: baixando proposições…")
        props = ler_csv(f"{BASE}/proposicoes/csv/proposicoes-{ano}.csv")
        print(f"  {len(props)} proposições no arquivo")
        if props:
            print("  colunas:", ", ".join(list(props[0].keys())[:40]))
        print(f"Ano {ano}: baixando temas…")
        temas = ler_csv(f"{BASE}/proposicoesTemas/csv/proposicoesTemas-{ano}.csv")
        tema_penal = {}
        for t in temas:
            uri = g(t, "uriProposicao")
            pid = uri.rstrip("/").split("/")[-1] if uri else g(t, "idProposicao")
            nome = g(t, "tema")
            if pid:
                tema_penal.setdefault(pid, set()).add(nome)
        print(f"Ano {ano}: baixando autores…")
        try:
            autores_rows = ler_csv(f"{BASE}/proposicoesAutores/csv/proposicoesAutores-{ano}.csv")
        except RuntimeError:
            autores_rows = []
        autores = {}
        for a in autores_rows:
            pid = g(a, "idProposicao") or g(a, "uriProposicao").rstrip("/").split("/")[-1]
            nome = g(a, "nomeAutor")
            if not pid or not nome:
                continue
            partido, uf = g(a, "siglaPartidoAutor"), g(a, "siglaUFAutor")
            rot = nome + (f" ({partido}/{uf})" if partido and uf else "")
            try:
                ordem = int(g(a, "ordemAssinatura") or 999)
            except ValueError:
                ordem = 999
            autores.setdefault(pid, []).append((ordem, rot))

        for p in props:
            sigla = g(p, "siglaTipo")
            if sigla not in TIPOS:
                continue
            analisadas += 1
            pid = str(g(p, "id"))
            ementa = (g(p, "ementa") or "").strip()
            temas_p = tema_penal.get(pid, set())
            por_tema = any("penal" in t.lower() for t in temas_p)
            if not (por_tema or PENAL.search(ementa)):
                continue
            texto = ementa + " " + (g(p, "ementaDetalhada") or "") + " " + (g(p, "keywords") or "")
            situacao = g(p, "ultimoStatus_descricaoSituacao")
            lista_aut = [r for _, r in sorted(autores.get(pid, []))]
            itens[pid] = {
                "id": int(pid),
                "casa": "Câmara",
                "sigla": sigla,
                "numero": int(g(p, "numero") or 0),
                "ano": int(g(p, "ano") or ano),
                "ementa": ementa,
                "apresentacao": (g(p, "dataApresentacao") or "")[:10],
                "autores": lista_aut[:6],
                "n_autores": len(lista_aut),
                "situacao": situacao,
                "em_tramitacao": not ENCERRADA.search(situacao or ""),
                "orgao": g(p, "ultimoStatus_siglaOrgao"),
                "ultima_tramitacao": (g(p, "ultimoStatus_dataHora") or "")[:10],
                "descricao_tramitacao": g(p, "ultimoStatus_descricaoTramitacao"),
                "url": f"https://www.camara.leg.br/propostas-legislativas/{pid}",
                "inteiro_teor": g(p, "urlInteiroTeor"),
                "temas": sorted(temas_p),
                "por_tema": por_tema,
                "diplomas": [n for n, rx in DIPLOMAS if rx.search(texto)],
                "natureza": [n for n, rx in NATUREZA if rx.search(texto)],
            }
        print(f"  selecionadas até agora: {len(itens)}")

    dados = sorted(itens.values(), key=lambda x: (x["apresentacao"], x["id"]), reverse=True)
    saida = {
        "atualizado_em": HOJE.strftime("%Y-%m-%d %H:%M"),
        "fonte": "Câmara dos Deputados, dados abertos (arquivos anuais de proposições, temas e autores)",
        "anos": ANOS,
        "tipos": sorted(TIPOS),
        "analisadas": analisadas,
        "total": len(dados),
        "itens": dados,
    }
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Gravado {SAIDA}: {len(dados)} proposições penais de {analisadas} analisadas")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Monitor de proposições penais no Senado Federal.

Consulta a API de dados abertos do Senado (https://legis.senado.leg.br/dadosabertos):
1. processos das classes "Direito Penal e Penitenciário" e "Processo Penal" apresentados
   desde o início da legislatura;
2. todos os PL, PLP e PEC apresentados no período, mês a mês, para a seleção por
   palavras-chave na ementa (mesmos critérios do monitor da Câmara).
Entram as proposições iniciadas no Senado ("Iniciadora"). As que vieram da Câmara
("Revisora") são gravadas à parte, para indicar no painel que a proposição da Câmara
está em revisão no Senado.

Grava data/monitor/senado.json.
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from monitor_camara import PENAL, DIPLOMAS, NATUREZA, HOJE, INICIO_LEGISLATURA, LEGISLATURA  # noqa: E402

BASE = "https://legis.senado.leg.br/dadosabertos"
TIPOS = {"PL", "PLP", "PEC"}
CLASSES = {33805617: "Direito Penal e Penitenciário", 33805422: "Processo Penal"}
SAIDA = os.path.join(os.path.dirname(__file__), "..", "data", "monitor", "senado.json")


def api(caminho, **params):
    url = f"{BASE}{caminho}?{urllib.parse.urlencode(params, doseq=True)}"
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "monitor-penal (site academico)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                dados = json.loads(r.read().decode("utf-8"))
                return dados if isinstance(dados, list) else []
        except Exception as e:  # noqa: BLE001
            print(f"  falha ({i+1}/4) em {url}: {e}", file=sys.stderr)
            time.sleep(4 * (i + 1))
    raise RuntimeError(f"não foi possível consultar {url}")


def meses(inicio, fim):
    d = date.fromisoformat(inicio)
    while d <= fim:
        prox = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
        yield d.isoformat(), min(prox - timedelta(days=1), fim).isoformat()
        d = prox


AUTOR = re.compile(r"[\s,]*(?:e\s+)?(?:Senador(?:a)?\s+|Deputad[oa]\s+)?([^,()]+?)\s*\(([^/()]+)/([A-Z]{2})\)")


def autores(texto):
    texto = (texto or "").strip()
    achados = [[n.strip(), p.strip(), u] for n, p, u in AUTOR.findall(texto)]
    return achados or ([[texto, "", ""]] if texto else [])


def ident(s):
    m = re.match(r"^\s*([A-Z]+)\s+(\d+)/(\d{4})", s or "")
    return (m.group(1), int(m.group(2)), int(m.group(3))) if m else (None, None, None)


def situacao_legivel(s):
    s = (s or "").strip()
    if not s.isupper():
        return s
    s = s[:1].upper() + s[1:].lower()
    for nome in ("Câmara dos Deputados", "Senado Federal", "Congresso Nacional", "Plenário", "Presidente da República", "Mesa", "Ordem do Dia", "Constituição"):
        s = re.sub(re.escape(nome.lower()), nome, s)
    return s


def main():
    fim = HOJE.date()
    registros, por_classe, diag = {}, {}, {"consultas": 0}

    for cod, nome in CLASSES.items():
        lista = api("/processo", codigoClasse=cod, dataInicioApresentacao=INICIO_LEGISLATURA, dataFimApresentacao=fim.isoformat())
        diag["consultas"] += 1
        diag[f"classe_{cod}"] = len(lista)
        for x in lista:
            registros[x["id"]] = x
            por_classe.setdefault(x["id"], set()).add(nome)

    for sigla in sorted(TIPOS):
        for ini, fi in meses(INICIO_LEGISLATURA, fim):
            lista = api("/processo", sigla=sigla, dataInicioApresentacao=ini, dataFimApresentacao=fi)
            diag["consultas"] += 1
            for x in lista:
                registros.setdefault(x["id"], x)
    diag["registros"] = len(registros)

    itens, revisao, analisadas = [], {}, 0
    for pid, x in registros.items():
        sigla, numero, ano = ident(x.get("identificacao"))
        if sigla not in TIPOS:
            continue
        apres = (x.get("dataApresentacao") or "")[:10]
        if not apres or apres < INICIO_LEGISLATURA:
            continue
        ementa = (x.get("ementa") or "").strip()
        classes = sorted(por_classe.get(pid, set()))
        penal = bool(classes) or bool(PENAL.search(ementa))
        objetivo = x.get("objetivo") or ""
        cod = x.get("codigoMateria")
        url = f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{cod}" if cod else ""
        situacao = situacao_legivel(x.get("situacaoAtual"))
        if objetivo == "Revisora":
            if penal:
                revisao[f"{sigla} {numero}/{ano}"] = {"casa": "Senado", "situacao": situacao, "data": (x.get("dataSituacaoAtual") or "")[:10], "url": url, "tramitando": x.get("tramitando") == "Sim"}
            continue
        if objetivo != "Iniciadora":
            continue
        analisadas += 1
        if not penal:
            continue
        itens.append({
            "id": pid,
            "casa": "Senado",
            "sigla": sigla,
            "numero": numero,
            "ano": ano,
            "ementa": ementa,
            "apresentacao": apres,
            "aut": autores(x.get("autoria")),
            "situacao": situacao,
            "em_tramitacao": x.get("tramitando") == "Sim",
            "orgao": "",
            "ultima_tramitacao": (x.get("dataSituacaoAtual") or "")[:10],
            "url": url,
            "tramitacao": url,
            "inteiro_teor": x.get("urlDocumento") or "",
            "temas": classes,
            "por_tema": bool(classes),
            "diplomas": [n for n, rx in DIPLOMAS if rx.search(ementa)],
            "natureza": [n for n, rx in NATUREZA if rx.search(ementa)],
        })

    itens.sort(key=lambda i: (i["apresentacao"], i["id"]), reverse=True)
    diag["revisoras_penais"] = len(revisao)
    saida = {
        "atualizado_em": HOJE.strftime("%Y-%m-%d %H:%M"),
        "fonte": "Senado Federal, API de dados abertos legislativos (processos)",
        "legislatura": LEGISLATURA,
        "inicio": INICIO_LEGISLATURA,
        "tipos": sorted(TIPOS),
        "analisadas": analisadas,
        "total": len(itens),
        "diagnostico": diag,
        "revisao": revisao,
        "itens": itens,
    }
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Gravado {SAIDA}: {len(itens)} proposições penais iniciadas no Senado de {analisadas} analisadas; {len(revisao)} da Câmara em revisão")


if __name__ == "__main__":
    main()

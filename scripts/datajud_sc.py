#!/usr/bin/env python3
"""Justiça criminal em SC: agregados da API Pública do DataJud (CNJ) para o TJSC.

Grava data/datajud/sc.json, lido por ferramentas/justica-criminal-sc.html.
Só usa contagens agregadas (classe, assunto, órgão julgador, grau, mês de ajuizamento);
a API não traz partes nem processos sigilosos.
Documentação: https://datajud-wiki.cnj.jus.br/api-publica/
"""
import json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

URL = "https://api-publica.datajud.cnj.jus.br/api_publica_tjsc/_search"
WIKI = "https://datajud-wiki.cnj.jus.br/api-publica/acesso/"
# Chave pública divulgada pelo CNJ na página de acesso; lida da wiki a cada execução, porque pode mudar.
CHAVE_RESERVA = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
SAIDA = os.path.join(os.path.dirname(__file__), "..", "data", "datajud", "sc.json")
ANO_INICIAL = 2020

ACOES_PENAIS = [
    "Ação Penal - Procedimento Ordinário",
    "Ação Penal - Procedimento Sumário",
    "Ação Penal - Procedimento Sumaríssimo",
    "Ação Penal de Competência do Júri",
    "Procedimento Especial da Lei Antitóxicos",
    "Crimes de Calúnia, Injúria e Difamação de Competência do Juiz Singular",
]
GRUPOS = {
    "acoes": ACOES_PENAIS,
    "inq": ["Inquérito Policial"],
    "tc": ["Termo Circunstanciado"],
    "exec": ["Execução da Pena", "Execução de Pena de Multa", "Execução de Medidas Alternativas no Juízo Comum"],
    "rec": ["Apelação Criminal", "Habeas Corpus Criminal", "Agravo de Execução Penal", "Recurso em Sentido Estrito", "Revisão Criminal"],
}
CRIMINAL = re.compile(r"Penal|Criminal|Inquérito|Termo Circunstanciado|Habeas|Prisão|Pena\b|Antitóxicos|Júri|Liberdade Provisória|Medidas Alternativas|Queixa|Restituição de Coisas|Calúnia|Persecução", re.I)


def chave():
    try:
        html = urllib.request.urlopen(urllib.request.Request(WIKI, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode("utf-8", "replace")
        m = re.search(r"APIKey\s+([A-Za-z0-9+/=]{40,})", html)
        if m:
            return m.group(1)
    except Exception as e:
        print("Aviso: chave não lida da wiki:", e, file=sys.stderr)
    return CHAVE_RESERVA


def consulta(corpo, k, tentativas=4):
    dados = json.dumps(corpo).encode()
    for i in range(tentativas):
        try:
            req = urllib.request.Request(URL, data=dados, headers={"Authorization": "APIKey " + k, "Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=300).read())
            if "error" in r:
                raise RuntimeError(json.dumps(r["error"])[:300])
            return r
        except Exception as e:
            print(f"Tentativa {i + 1} falhou: {e}", file=sys.stderr)
            time.sleep(15 * (i + 1))
    raise SystemExit("DataJud não respondeu.")


def faixa(ini, fim):
    return {"range": {"dataAjuizamento": {"gte": ini, "lt": fim}}}


def ano(a, k):
    corpo = {
        "size": 0, "track_total_hits": True,
        "query": faixa(f"{a}0101000000", f"{a + 1}0101000000"),
        "aggs": {
            "classes": {"terms": {"field": "classe.nome.keyword", "size": 400}},
            "ap": {
                "filter": {"terms": {"classe.nome.keyword": ACOES_PENAIS}},
                "aggs": {
                    "assuntos": {"terms": {"field": "assuntos.nome.keyword", "size": 30}},
                    "orgaos": {"terms": {"field": "orgaoJulgador.nome.keyword", "size": 600}},
                    "grau": {"terms": {"field": "grau.keyword"}},
                },
            },
            "max": {"max": {"field": "dataAjuizamento"}},
        },
    }
    r = consulta(corpo, k)
    a_ = r["aggregations"]
    classes = {b["key"].strip(): b["doc_count"] for b in a_["classes"]["buckets"]}
    return a, {
        "total": r["hits"]["total"]["value"],
        "grupos": {g: sum(classes.get(c, 0) for c in cs) for g, cs in GRUPOS.items()},
        "classes": dict(sorted(((c, n) for c, n in classes.items() if CRIMINAL.search(c)), key=lambda x: -x[1])),
        "acoes": a_["ap"]["doc_count"],
        "assuntos": [[b["key"].strip(), b["doc_count"]] for b in a_["ap"]["assuntos"]["buckets"]],
        "orgaos": [[b["key"].strip(), b["doc_count"]] for b in a_["ap"]["orgaos"]["buckets"]],
        "grau": {b["key"]: b["doc_count"] for b in a_["ap"]["grau"]["buckets"]},
        "max": a_["max"].get("value"),
    }


def meses(k, n=36):
    hoje = date.today()
    lista = []
    y, m = hoje.year, hoje.month
    for _ in range(n):
        lista.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    lista.reverse()
    ranges = []
    for (y, m) in lista:
        y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
        ranges.append({"key": f"{y}-{m:02d}", "from": f"{y}{m:02d}01000000", "to": f"{y2}{m2:02d}01000000"})
    sub = {"m": {"range": {"field": "dataAjuizamento", "ranges": ranges}}}
    corpo = {
        "size": 0,
        "query": faixa(ranges[0]["from"], ranges[-1]["to"]),
        "aggs": {g: {"filter": {"terms": {"classe.nome.keyword": cs}}, "aggs": sub} for g, cs in GRUPOS.items() if g in ("acoes", "inq", "tc")},
    }
    r = consulta(corpo, k)
    out = []
    for i, rg in enumerate(ranges):
        out.append({"mes": rg["key"], **{g: r["aggregations"][g]["m"]["buckets"][i]["doc_count"] for g in ("acoes", "inq", "tc")}})
    return out


def comarca(nome):
    m = re.search(r"Comarca d[aeo]s? (.+)$", nome)
    return m.group(1).strip() if m else None


def main():
    k = chave()
    anos = list(range(ANO_INICIAL, date.today().year + 1))
    with ThreadPoolExecutor(max_workers=4) as ex:
        fut_m = ex.submit(meses, k)
        res = dict(ex.map(lambda a: ano(a, k), anos))
        serie = fut_m.result()
    maxv = max((v["max"] or 0) for v in res.values())
    s = str(int(maxv)) if maxv else ""
    base_ate = f"{s[6:8]}/{s[4:6]}/{s[0:4]}" if len(s) >= 8 else ""
    # meses posteriores à data-base ficam fora da série (a base do CNJ chega com atraso)
    if len(s) >= 6:
        lim = f"{s[0:4]}-{s[4:6]}"  # mês da data-base é parcial e fica fora
        serie = [x for x in serie if x["mes"] < lim]
    for a, v in res.items():
        com = {}
        outros = 0
        for nome, n in v.pop("orgaos"):
            c = comarca(nome)
            if c:
                com[c] = com.get(c, 0) + n
            else:
                outros += n
        v["comarcas"] = sorted(com.items(), key=lambda x: -x[1])
        v["sem_comarca"] = outros
        v.pop("max")
    dados = {
        "fonte": "API Pública do DataJud (CNJ), índice do TJSC",
        "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_ate": base_ate,
        "grupos_classes": GRUPOS,
        "anos": {str(a): res[a] for a in anos},
        "meses": serie,
    }
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
    print("Gravado:", SAIDA, "| base até", base_ate, "| ações penais por ano:", {a: res[a]["acoes"] for a in anos})


if __name__ == "__main__":
    main()

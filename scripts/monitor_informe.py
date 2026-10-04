#!/usr/bin/env python3
"""Informe semanal do Monitor Legislativo Penal.

Lê data/monitor/proposicoes.json e registra em data/monitor/vistos.json a data em que
cada proposição entrou na base do monitor. O informe lista as proposições que entraram
na base nos 7 dias completos anteriores à execução (a Câmara e o Senado classificam o
tema com atraso, de modo que a data de entrada é mais fiel do que a data de apresentação
para dizer o que é novo na semana).

Grava data/monitor/informe-semanal.json e data/monitor/informe-semanal.md.
Na primeira execução, sem vistos.json, a data de entrada de cada proposição é a de
apresentação, para que o acervo anterior não apareça como novidade.
"""
import json, os, sys
from collections import Counter
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from monitor_camara import HOJE  # noqa: E402

PASTA = os.path.join(os.path.dirname(__file__), "..", "data", "monitor")
PAINEL = "https://luizeduardodc-adv.github.io/ferramentas/monitor-legislativo.html"
CASAS = (("Câmara", "Câmara dos Deputados"), ("Senado", "Senado Federal"))


def br(d):
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if d else ""


def chave(x):
    return f'{x["sigla"]} {x["numero"]}/{x["ano"]}'


def autores(x):
    aut = x.get("aut") or []
    if not aut:
        return "autoria não informada"
    nome, partido, uf = aut[0]
    s = f"{nome} ({partido}/{uf})" if partido and uf else nome
    return s + (f" e mais {len(aut) - 1}" if len(aut) > 1 else "")


def contagem(c, limite=None):
    itens = c.most_common(limite)
    return "; ".join(f"{k} {v}" for k, v in itens) if itens else "nenhuma"


def main():
    with open(os.path.join(PASTA, "proposicoes.json"), encoding="utf-8") as f:
        base = json.load(f)
    caminho_vistos = os.path.join(PASTA, "vistos.json")
    primeira = not os.path.exists(caminho_vistos)
    vistos = {} if primeira else json.load(open(caminho_vistos, encoding="utf-8"))

    hoje = HOJE.date().isoformat()
    for x in base["itens"]:
        k = chave(x)
        if k not in vistos:
            vistos[k] = (x.get("apresentacao") or hoje) if primeira else hoje
    with open(caminho_vistos, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(vistos.items())), f, ensure_ascii=False, separators=(",", ":"))

    fim = HOJE.date() - timedelta(days=1)
    ini = fim - timedelta(days=6)
    ini_s, fim_s = ini.isoformat(), fim.isoformat()
    novas = [x for x in base["itens"] if ini_s <= vistos[chave(x)] <= fim_s]
    novas.sort(key=lambda x: (x["casa"] != "Câmara", x.get("apresentacao", ""), x["numero"]), reverse=False)

    casa = Counter(x["casa"] for x in novas)
    tipo = Counter(x["sigla"] for x in novas)
    natureza = Counter(n for x in novas for n in x.get("natureza", []))
    diploma = Counter(d for x in novas for d in x.get("diplomas", []))
    partido = Counter(x["aut"][0][1] for x in novas if x.get("aut") and x["aut"][0][1])
    na_semana = sum(1 for x in novas if ini_s <= x.get("apresentacao", "") <= fim_s)

    L = [
        f"Proposições penais da semana | {br(ini_s)} a {br(fim_s)}",
        "",
        f"Fonte: Monitor Legislativo Penal, a partir dos dados abertos da Câmara dos Deputados e do Senado Federal, "
        f"{base.get('legislatura', '')}. Base atualizada em {br(base.get('atualizado_em', '')[:10])}. Painel: {PAINEL}",
        "",
        "Em números",
        "",
    ]
    if not novas:
        L.append("1. Nenhuma proposição penal nova entrou na base nesta semana.")
    else:
        L += [
            f"1. {len(novas)} proposições novas na base (Câmara {casa.get('Câmara', 0)}; Senado {casa.get('Senado', 0)}).",
            f"2. Por tipo: {contagem(tipo)}.",
            f"3. Apresentadas na própria semana: {na_semana}; apresentadas antes e incorporadas agora: {len(novas) - na_semana} "
            "(as Casas atribuem o tema com alguns dias ou semanas de atraso).",
            f"4. Natureza (classificação automática pela ementa): {contagem(natureza)}.",
            f"5. Diplomas alterados (classificação automática pela ementa): {contagem(diploma)}.",
            f"6. Partido do autor principal: {contagem(partido, 8)}.",
        ]
    for sigla_casa, nome_casa in CASAS:
        grupo = [x for x in novas if x["casa"] == sigla_casa]
        if not grupo:
            continue
        L += ["", f"Iniciadas no {nome_casa}" if sigla_casa == "Senado" else f"Iniciadas na {nome_casa}", ""]
        for i, x in enumerate(grupo, 1):
            extra = []
            if x.get("natureza"):
                extra.append("Natureza: " + ", ".join(x["natureza"]).lower() + ".")
            if x.get("diplomas"):
                extra.append("Altera: " + ", ".join(x["diplomas"]) + ".")
            L.append(f"{i}. {chave(x)} – {autores(x)} – apresentada em {br(x.get('apresentacao', ''))}")
            L.append(f"   {x.get('ementa', '').strip()}")
            if extra:
                L.append("   " + " ".join(extra))
            L.append(f"   Situação: {x.get('situacao') or 'não informada'}. Tramitação: {x.get('tramitacao') or x.get('url')}")
    md = "\n".join(L) + "\n"

    saida = {
        "gerado_em": HOJE.strftime("%Y-%m-%d %H:%M"),
        "periodo": {"inicio": ini_s, "fim": fim_s},
        "total": len(novas),
        "por_casa": dict(casa),
        "por_tipo": dict(tipo),
        "apresentadas_na_semana": na_semana,
        "natureza": dict(natureza),
        "diplomas": dict(diploma),
        "partidos": dict(partido),
        "itens": [{k: x.get(k) for k in ("casa", "sigla", "numero", "ano", "ementa", "apresentacao", "aut", "situacao", "tramitacao", "natureza", "diplomas")} for x in novas],
    }
    with open(os.path.join(PASTA, "informe-semanal.json"), "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    with open(os.path.join(PASTA, "informe-semanal.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Informe {ini_s} a {fim_s}: {len(novas)} proposições ({dict(casa)}); vistos.json com {len(vistos)} chaves{' (semeado)' if primeira else ''}")


if __name__ == "__main__":
    main()

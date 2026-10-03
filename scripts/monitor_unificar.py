#!/usr/bin/env python3
"""Unifica os dados da Câmara e do Senado em data/monitor/proposicoes.json.

Chave comum: sigla, número e ano (numeração unificada do Congresso desde 2019).
1. Proposição iniciada no Senado que também aparece nos arquivos da Câmara: fica o
   registro do Senado (casa de origem), com a situação e o link da Câmara em "outra".
2. Proposição da Câmara em revisão no Senado: ganha em "outra" a situação e o link do Senado.
"""
import json, os

PASTA = os.path.join(os.path.dirname(__file__), "..", "data", "monitor")


def ler(nome):
    try:
        with open(os.path.join(PASTA, nome), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def chave(x):
    return f'{x["sigla"]} {x["numero"]}/{x["ano"]}'


def main():
    cam, sen = ler("camara.json"), ler("senado.json")
    if not cam:
        raise SystemExit("camara.json ausente")
    cam_itens = cam["itens"]
    for x in cam_itens:
        x.setdefault("casa", "Câmara")
    sen_itens = (sen or {}).get("itens", [])
    revisao = (sen or {}).get("revisao", {})

    por_chave_cam = {chave(x): x for x in cam_itens}
    unidos, removidos_cam = [], set()
    for s in sen_itens:
        k = chave(s)
        c = por_chave_cam.get(k)
        if c:
            s["outra"] = {"casa": "Câmara", "situacao": c.get("situacao", ""), "data": c.get("ultima_tramitacao", ""), "url": c.get("tramitacao") or c.get("url", ""), "tramitando": c.get("em_tramitacao", True)}
            for campo in ("diplomas", "natureza"):
                s[campo] = sorted(set(s[campo]) | set(c.get(campo, [])))
            removidos_cam.add(k)
        unidos.append(s)
    for c in cam_itens:
        k = chave(c)
        if k in removidos_cam:
            continue
        if k in revisao:
            c["outra"] = revisao[k]
        unidos.append(c)

    unidos.sort(key=lambda i: (i.get("apresentacao", ""), str(i["id"])), reverse=True)
    saida = {
        "atualizado_em": max(cam.get("atualizado_em", ""), (sen or {}).get("atualizado_em", "")),
        "fonte": "Câmara dos Deputados e Senado Federal, dados abertos",
        "legislatura": cam.get("legislatura"),
        "inicio": cam.get("inicio"),
        "tipos": cam.get("tipos"),
        "casas": {
            "Câmara": {"analisadas": cam.get("analisadas", 0), "selecionadas": len([x for x in unidos if x["casa"] == "Câmara"])},
            "Senado": {"analisadas": (sen or {}).get("analisadas", 0), "selecionadas": len([x for x in unidos if x["casa"] == "Senado"]), "disponivel": bool(sen)},
        },
        "analisadas": cam.get("analisadas", 0) + (sen or {}).get("analisadas", 0),
        "total": len(unidos),
        "itens": unidos,
    }
    with open(os.path.join(PASTA, "proposicoes.json"), "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    print(f"proposicoes.json: {len(unidos)} itens ({saida['casas']})")


if __name__ == "__main__":
    main()

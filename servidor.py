"""Servidor do painel CS Questor, independente do QA Hub.

Por que existir: o painel morava dentro do QA Hub (porta 8000), como template
Jinja envolvido em {% raw %}. Isso obrigava a copiar um arquivo de 2 MB para
outro projeto a cada geracao, e amarrava a publicacao ao ciclo de vida daquele
app. Aqui o painel e servido do proprio arquivo que painel.py gera, sem copia e
sem Jinja, entao o envoltorio raw deixou de ser necessario.

A pagina traz nome de cliente, CNPJ, MRR e o texto literal dos chamados. Por
isso duas travas:

  1. Escuta em 127.0.0.1 por padrao. Abrir na rede exige --host 0.0.0.0, que e
     uma decisao consciente e nao um acidente de configuracao.

  2. Exige login. A senha nunca e gravada: o que fica no disco e um hash
     pbkdf2, e o arquivo com ele esta no .gitignore.

    python servidor.py
    python servidor.py --host 0.0.0.0 --porta 8050
    python servidor.py --definir-usuario admin        (pede a senha e sai)
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, render_template_string,
                   request, session)

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import acesso  # noqa: E402

RAIZ = Path(__file__).resolve().parent
PAGINA = RAIZ / "dashboard" / "index.html"
ACESSO = RAIZ / "dados" / "acesso.json"

HOST_PADRAO = os.environ.get("PAINEL_HOST", "127.0.0.1")
PORTA_PADRAO = int(os.environ.get("PAINEL_PORTA", "8050"))

SESSAO_HORAS = 12
LIVRES = {"/login", "/saude"}

# Freio de forca bruta. Nao e rate limit de verdade, e proposital: guardar
# estado em memoria basta para uma porta de rede interna, e nao adiciona
# dependencia nenhuma. Reinicio zera, o que e aceitavel aqui.
TENTATIVAS_ATE_ESPERAR = 5
ESPERA_SEGUNDOS = 60
_falhas: dict[str, list[float]] = defaultdict(list)

app = Flask(__name__)


# --------------------------------------------------------------------- acesso
def definir_usuario(nome: str, senha: str, perfil: str = "admin") -> None:
    """Cria ou troca a senha de um usuario pela linha de comando."""
    d = acesso.carregar()
    acesso.definir_usuario(d, nome, senha, perfil=perfil, trocar_senha=False)
    acesso.anotar(d, "linha de comando", f"definiu a senha de {nome}")
    acesso.gravar(d)


def _ficha() -> dict:
    """Usuario da sessao, ja com as telas do perfil resolvidas."""
    login = session.get("usuario") or ""
    d = acesso.carregar()
    u = d["usuarios"].get(login)
    if not u or not u.get("ativo"):
        return {}
    return {"login": login, "u": u, "d": d,
            "telas": acesso.telas_de(d, login),
            "gerir": acesso.pode_gerir(d, login)}


def _token() -> str:
    """Token simples contra postagem de outro site. Vive na sessao."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def _token_ok() -> bool:
    enviado = request.form.get("csrf") or ""
    guardado = session.get("csrf") or ""
    return bool(guardado) and secrets.compare_digest(enviado, guardado)


def _bloqueado(ip: str) -> int:
    agora = time.time()
    _falhas[ip] = [t for t in _falhas[ip] if agora - t < ESPERA_SEGUNDOS]
    if len(_falhas[ip]) < TENTATIVAS_ATE_ESPERAR:
        return 0
    return int(ESPERA_SEGUNDOS - (agora - _falhas[ip][0])) + 1


# ---------------------------------------------------------------------- telas
LOGIN = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CS Questor</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--acento:#ED5F2C;--barra:#1B1B1D;--fundo:#FFFFFF;--sup:#FCFCFC;
  --tinta:#18181B;--tinta2:#57564F;--tinta3:#8C8A83;--borda:#E7E6E2;--grave:#B4211C}
@media (prefers-color-scheme:dark){:root{--fundo:#0F0F11;--sup:#161618;
  --tinta:#FAFAF9;--tinta2:#A8A6A0;--tinta3:#76746E;--borda:#292927;--grave:#F08A85}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--fundo);
  color:var(--tinta);font:14px/1.55 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;
  padding:24px}
form{width:100%;max-width:340px;background:var(--sup);border:1px solid var(--borda);
  border-radius:14px;padding:26px 24px}
.marca{display:flex;align-items:center;gap:9px;font-weight:600;margin-bottom:4px}
.sigla{width:26px;height:26px;border-radius:6px;display:grid;place-items:center;
  background:var(--acento);color:#fff;font-size:13px;font-weight:700}
p.sub{margin:0 0 20px;color:var(--tinta3);font-size:12.5px}
label{display:block;font-size:10.5px;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;color:var(--tinta3);margin:0 0 5px}
input{width:100%;padding:9px 11px;border:1px solid var(--borda);border-radius:9px;
  background:var(--fundo);color:var(--tinta);font:14px/1.5 inherit;margin-bottom:14px}
input:focus{outline:2px solid var(--acento);outline-offset:1px}
button{width:100%;padding:10px;border:0;border-radius:9px;background:var(--acento);
  color:#fff;font:600 14px/1.4 inherit;cursor:pointer}
button:hover{filter:brightness(1.06)}
.erro{margin:0 0 14px;padding:9px 11px;border-radius:9px;font-size:12.5px;
  border:1px solid var(--grave);color:var(--grave)}
</style></head><body>
<form method="post" action="/login">
  <div class="marca"><span class="sigla">Q</span> CS Questor</div>
  <p class="sub">Cancelamentos e atendimentos</p>
  {% if erro %}<p class="erro">{{ erro }}</p>{% endif %}
  <label for="usuario">Usuário</label>
  <input id="usuario" name="usuario" autocomplete="username" autofocus required>
  <label for="senha">Senha</label>
  <input id="senha" name="senha" type="password" autocomplete="current-password" required>
  <button type="submit">Entrar</button>
</form></body></html>"""


@app.before_request
def _exigir_login():
    if request.path in LIVRES or request.path.startswith("/static/"):
        return
    if not session.get("usuario"):
        return redirect("/login")
    f = _ficha()
    if not f:                       # desativado ou removido enquanto navegava
        session.clear()
        return redirect("/login")
    # senha provisoria: nao solta a pessoa no painel antes de trocar
    if f["u"].get("trocar_senha") and request.path not in ("/trocar-senha", "/sair"):
        return redirect("/trocar-senha")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("usuario"):
            return redirect("/")
        return render_template_string(LOGIN, erro=None)

    ip = request.remote_addr or "?"
    espera = _bloqueado(ip)
    if espera:
        return render_template_string(
            LOGIN, erro=f"Muitas tentativas. Tente de novo em {espera}s."), 429

    nome = acesso.normalizar_login(request.form.get("usuario"))
    d = acesso.carregar()
    u = acesso.conferir(d, nome, request.form.get("senha") or "")
    if u:
        _falhas.pop(ip, None)
        session.permanent = True
        session["usuario"] = nome
        u["ultimo_acesso"] = datetime.now().isoformat(timespec="seconds")
        acesso.anotar(d, nome, "entrou")
        acesso.gravar(d)
        return redirect("/trocar-senha" if u.get("trocar_senha") else "/")
    _falhas[ip].append(time.time())
    acesso.anotar(d, nome or "?", f"tentativa de senha errada ({ip})")
    acesso.gravar(d)
    return render_template_string(LOGIN, erro="Usuário ou senha não conferem."), 401


@app.route("/sair")
def sair():
    session.clear()
    return redirect("/login")


# ---------------------------------------------------------------------- painel
def _sem_cache(resposta: Response) -> Response:
    """O painel e regerado por fora; cache do navegador esconderia a versao nova.

    Ja custou tempo uma vez: a pagina nao mudava depois de regerada porque o
    Flask servia do cache de template. Aqui nao ha template, mas o navegador
    faria o mesmo estrago sozinho.
    """
    resposta.headers["Cache-Control"] = "no-store, must-revalidate"
    resposta.headers["Pragma"] = "no-cache"
    return resposta


_CACHE: dict[tuple, str] = {}


def _pagina_para(telas: list[str]) -> str:
    """Monta a versao do painel deste perfil, sem os dados das outras telas.

    E aqui que a permissao vira protecao de verdade. Esconder o item de menu no
    navegador nao adianta: o JSON inteiro ja teria sido entregue e apareceria em
    "exibir codigo-fonte". A aba Atencao sozinha sao 1,3 MB com trecho de
    chamado e nome de cliente dentro.
    """
    chave = (tuple(sorted(telas)), PAGINA.stat().st_mtime_ns)
    pronta = _CACHE.get(chave)
    if pronta:
        return pronta
    bruto = PAGINA.read_text(encoding="utf-8")
    marca = "const DADOS = "
    i = bruto.index(marca) + len(marca)
    j = bruto.index("\n", i)
    dados = json.loads(bruto[i:j].rstrip().rstrip(";"))
    manter = acesso.chaves_de_dados(telas)
    enxuto = {k: v for k, v in dados.items() if k in manter}
    # </ dentro de string quebraria o bloco de script, como em painel.py
    corpo = (bruto[:i] + json.dumps(enxuto, ensure_ascii=False).replace("</", "<\\/")
             + ";" + bruto[j:])
    inj = ("<script>window.TELAS_PERMITIDAS="
           + json.dumps(telas, ensure_ascii=False) + ";</script>\n")
    k = corpo.rindex("<script>")
    pronta = corpo[:k] + inj + corpo[k:]
    _CACHE.clear()                  # uma versao por vez basta; evita crescer sem fim
    _CACHE[chave] = pronta
    return pronta


@app.route("/")
def painel() -> Response:
    if not PAGINA.exists():
        abort(503, "dashboard/index.html nao existe. Rode: python src/painel.py")
    f = _ficha()
    if not f["telas"]:
        return _sem_cache(Response(
            render_template_string(SEM_TELAS, nome=f["u"].get("nome")),
            mimetype="text/html; charset=utf-8"))
    html = _pagina_para(f["telas"])
    rodape = _rodape(f["u"].get("nome") or f["login"], f["gerir"])
    html = html.replace("</body>", rodape + "</body>", 1)
    return _sem_cache(Response(html, mimetype="text/html; charset=utf-8"))


@app.route("/usabilidade-produto")
def compatibilidade() -> Response:
    """Endereco antigo, herdado do QA Hub. Redireciona para a raiz."""
    return redirect("/", code=302)


@app.route("/saude")
def saude() -> Response:
    """Fica sem login de proposito: e so um sinal de vida, sem dado de cliente."""
    if not PAGINA.exists():
        return jsonify({"ok": False, "erro": "pagina nao gerada"}), 503
    info = PAGINA.stat()
    gerado = datetime.fromtimestamp(info.st_mtime, tz=timezone.utc).astimezone()
    return jsonify({"ok": True, "kb": round(info.st_size / 1024),
                    "gerado_em": gerado.isoformat(timespec="seconds")})


# ------------------------------------------------------------------- execucao
# ------------------------------------------------------------------- acessos
_BOTAO = ("display:flex;align-items:center;gap:6px;padding:8px 13px;border-radius:999px;"
          "border:1px solid var(--borda);background:var(--sup);text-decoration:none;"
          "font:500 12.5px/1 Inter,system-ui,sans-serif")


def _rodape(nome: str, gerir: bool) -> str:
    """Barra fixa com quem esta logado, acessos e sair.

    Fica num canto fixo em vez de dentro do menu lateral porque o menu e montado
    pelo proprio painel, que nao sabe nada de sessao. Assim o servidor acrescenta
    isto sem mexer na navegacao.
    """
    acessos = (f'<a href="/acessos" title="Gerir acessos" '
               f'style="{_BOTAO};color:var(--tinta2)">&#9881; Acessos</a>') if gerir else ""
    return (
        '<div style="position:fixed;right:16px;bottom:16px;z-index:60;display:flex;'
        'align-items:center;gap:8px;box-shadow:0 2px 12px rgba(0,0,0,.16);'
        'border-radius:999px">'
        f'<span style="{_BOTAO};color:var(--tinta3);cursor:default" '
        f'title="Sessão de {nome}">&#128100; {nome}</span>'
        + acessos +
        f'<a href="/sair" style="{_BOTAO};color:var(--tinta2)" '
        f'title="Encerrar a sessão">&#9095; Sair</a></div>')

_BASE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ titulo }}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--acento:#ED5F2C;--fundo:#F7F7F8;--sup:#FFFFFF;--plano:#FFFFFF;--realce:#F4F4F5;
 --tinta:#18181B;--tinta2:#52525B;--tinta3:#8A8A93;--borda:#E8E8EA;--grade:#E8E8EA;
 --bom:#15803D;--grave:#B91C1C;--eixo:#D4D4D8}
@media (prefers-color-scheme:dark){:root{--fundo:#0A0A0B;--sup:#161618;--plano:#0F0F11;
 --realce:#1F1F23;--tinta:#FAFAFA;--tinta2:#A1A1AA;--tinta3:#71717A;--borda:#27272A;
 --grade:#27272A;--bom:#4ADE80;--grave:#F87171;--eixo:#3F3F46;--acento:#EA580C}}
*{box-sizing:border-box}
body{margin:0;background:var(--fundo);color:var(--tinta);
 font:14px/1.55 Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
.pg{max-width:1120px;margin:0 auto;padding:26px 22px}
a{color:var(--acento)}
h1{font-size:21px;font-weight:650;letter-spacing:-.02em;margin:0 0 3px}
.sub{font-size:12.5px;color:var(--tinta3);margin:0 0 22px}
.topo{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.topo .fim{margin-left:auto;font-size:12.5px}
section{background:var(--sup);border:1px solid var(--borda);border-radius:14px;
 padding:18px 20px;margin-bottom:20px}
section>header{display:flex;align-items:baseline;gap:10px;margin-bottom:4px}
.passo{width:22px;height:22px;flex:none;border-radius:6px;display:grid;place-items:center;
 background:color-mix(in srgb,var(--acento) 14%,transparent);color:var(--acento);
 font:700 11px/1 inherit}
h2{margin:0;font-size:15.5px;font-weight:650;flex:1}
.leg{margin:0 0 15px;padding-left:32px;font-size:12.5px;color:var(--tinta2);max-width:92ch}
.corpo{padding-left:32px}
button,input,select{font:inherit}
button{border-radius:9px;border:1px solid var(--borda);background:var(--plano);
 color:var(--tinta);padding:6px 13px;cursor:pointer;font-size:12.5px}
button:hover{border-color:var(--eixo)}
button.p{background:var(--acento);border-color:var(--acento);color:#fff;font-weight:600}
button.g{color:var(--grave);border-color:color-mix(in srgb,var(--grave) 40%,var(--borda))}
input,select{padding:8px 10px;border:1px solid var(--borda);border-radius:9px;
 background:var(--plano);color:var(--tinta);width:100%}
input:focus,select:focus{outline:2px solid var(--acento);outline-offset:1px}
label.c{display:block;font-size:10.5px;font-weight:700;letter-spacing:.08em;
 text-transform:uppercase;color:var(--tinta3);margin:0 0 5px}
.cx{border:1px solid var(--borda);border-radius:12px;overflow-x:auto;background:var(--plano)}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:680px}
th,td{text-align:left;padding:9px 11px;border-bottom:1px solid var(--grade);vertical-align:middle}
th{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--tinta3);
 font-weight:600;white-space:nowrap;background:var(--realce)}
tbody tr:last-child td{border-bottom:none}
.nome{font-weight:550;display:block}.mail{font-size:11.5px;color:var(--tinta3)}
.pill{display:inline-block;padding:1px 9px;border-radius:999px;font-size:11px;
 border:1px solid var(--borda);color:var(--tinta2);white-space:nowrap}
.pill.adm{border-color:var(--acento);color:var(--acento)}
.pill.on{border-color:var(--bom);color:var(--bom)}
.pill.off{border-color:var(--eixo);color:var(--tinta3)}
.acoes{display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap}
.acoes button{padding:4px 10px;font-size:11.5px}
.perfis{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr))}
.perfil{border:1px solid var(--borda);border-radius:12px;padding:15px 16px;background:var(--plano)}
.perfil>header{display:flex;align-items:center;gap:8px;margin-bottom:3px}
.perfil h3{margin:0;font-size:14px;font-weight:650;flex:1}
.perfil .qt{font-size:11.5px;color:var(--tinta3)}
.perfil p.d{margin:0 0 11px;font-size:12px;color:var(--tinta3);line-height:1.45}
.menus{display:grid;gap:5px;margin-bottom:11px}
.menus label{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--tinta2);cursor:pointer}
.menus input{accent-color:var(--acento);width:15px;height:15px;flex:none}
.menus .s{font-size:10px;color:var(--grave);border:1px solid var(--grave);
 border-radius:999px;padding:0 6px;margin-left:auto;white-space:nowrap}
.av{display:flex;gap:11px;border-radius:12px;padding:14px 16px;margin-bottom:22px;
 background:var(--sup);border:1px solid var(--borda);border-left:3px solid var(--grave);font-size:12.5px}
.av strong{display:block;margin-bottom:3px;font-size:13px}.av p{margin:0;color:var(--tinta2)}
.ok{border-left-color:var(--bom)}.ok .ic{color:var(--bom)}
.grade2{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(190px,100%),1fr));
 align-items:end;margin-bottom:12px}
.hint{font-size:11.5px;color:var(--tinta3);margin:10px 0 0}
.reg td{color:var(--tinta2);font-size:12.5px}.reg td.q{color:var(--tinta);font-weight:500}
</style></head><body><div class="pg">{{ corpo|safe }}</div></body></html>"""


SEM_TELAS = _BASE.replace("{{ corpo|safe }}", """
<h1>Sem telas liberadas</h1>
<p class="sub">Olá, {{ nome }}. O seu perfil ainda não tem nenhuma tela marcada.</p>
<div class="av"><span class="ic">&#9888;</span><div><strong>Fale com quem administra o painel</strong>
<p>O acesso existe, mas o perfil está vazio. Nada foi carregado nesta página.</p></div></div>
<p><a href="/sair">Sair</a></p>""").replace("{{ titulo }}", "CS Questor")


TROCAR = _BASE.replace("{{ corpo|safe }}", """
<h1>Troque a senha</h1>
<p class="sub">A senha atual é provisória. Escolha uma antes de entrar no painel.</p>
{% if erro %}<div class="av"><span class="ic">&#9888;</span><div>
<strong>Não deu</strong><p>{{ erro }}</p></div></div>{% endif %}
<section><div class="corpo" style="padding-left:0">
<form method="post" style="max-width:380px">
  <input type="hidden" name="csrf" value="{{ csrf }}">
  <label class="c" for="a">Senha nova</label>
  <input id="a" name="nova" type="password" autocomplete="new-password" required autofocus>
  <div style="height:12px"></div>
  <label class="c" for="b">Repita</label>
  <input id="b" name="repete" type="password" autocomplete="new-password" required>
  <div style="height:16px"></div>
  <button class="p" type="submit">Salvar e entrar</button>
</form>
<p class="hint">Mínimo de 10 caracteres. Ninguém vê a sua senha, nem quem administra.</p>
</div></section>""").replace("{{ titulo }}", "Trocar senha")


ACESSOS = _BASE.replace("{{ corpo|safe }}", """
<div class="topo"><div>
  <h1>Acessos</h1>
  <p class="sub">Quem entra no painel e quais telas cada um enxerga</p>
</div><span class="fim"><a href="/">voltar ao painel</a> · <a href="/sair">sair</a></span></div>

{% if aviso %}<div class="av ok"><span class="ic">&#10003;</span><div>
<strong>{{ aviso.titulo }}</strong><p>{{ aviso.texto }}</p></div></div>{% endif %}
{% if erro %}<div class="av"><span class="ic">&#9888;</span><div>
<strong>Não deu</strong><p>{{ erro }}</p></div></div>{% endif %}

<div class="av ok"><span class="ic">&#128274;</span><div>
<strong>A permissão vale no servidor, não no navegador</strong>
<p>O painel é um arquivo só, com {{ peso }} de dados dentro. Por isso o servidor monta
uma versão por perfil e remove do JSON o que aquele perfil não pode ver — o que a pessoa
não tem direito de ver não sai daqui, nem pelo código-fonte da página.</p></div></div>

<section><header><span class="passo">1</span><h2>Usuários</h2></header>
<p class="leg">Cada pessoa tem um perfil, e o perfil decide as telas. Trocar o perfil
vale no próximo carregamento, sem regerar nada.</p>
<div class="corpo">
  <div class="cx"><table>
    <thead><tr><th>Pessoa</th><th>Perfil</th><th>Último acesso</th><th>Situação</th>
    <th style="text-align:right">Ações</th></tr></thead><tbody>
    {% for u in usuarios %}<tr>
      <td><span class="nome">{{ u.nome }}</span><span class="mail">{{ u.login }}</span></td>
      <td><form method="post" action="/acessos/perfil-do-usuario" style="display:flex;gap:6px">
          <input type="hidden" name="csrf" value="{{ csrf }}">
          <input type="hidden" name="login" value="{{ u.login }}">
          <select name="perfil" style="width:auto;padding:4px 8px;font-size:12px">
            {% for k, p in perfis.items() %}
            <option value="{{ k }}" {% if k == u.perfil %}selected{% endif %}>{{ p.nome }}</option>
            {% endfor %}
          </select>
          <button type="submit" style="padding:4px 10px;font-size:11.5px">trocar</button>
        </form></td>
      <td>{{ u.ultimo or "—" }}</td>
      <td>{% if u.ativo %}<span class="pill on">ativo</span>{% else %}
          <span class="pill off">desativado</span>{% endif %}
          {% if u.trocar_senha %}<span class="pill">senha provisória</span>{% endif %}</td>
      <td><div class="acoes">
        <form method="post" action="/acessos/senha"><input type="hidden" name="csrf" value="{{ csrf }}">
          <input type="hidden" name="login" value="{{ u.login }}">
          <button type="submit">nova senha</button></form>
        {% if u.login != eu %}
        <form method="post" action="/acessos/ativo"><input type="hidden" name="csrf" value="{{ csrf }}">
          <input type="hidden" name="login" value="{{ u.login }}">
          <input type="hidden" name="ativo" value="{{ 0 if u.ativo else 1 }}">
          <button type="submit" class="{{ 'g' if u.ativo else '' }}">
            {{ "desativar" if u.ativo else "reativar" }}</button></form>
        {% endif %}
      </div></td>
    </tr>{% endfor %}
    </tbody></table></div>

  <form method="post" action="/acessos/usuario" style="margin-top:16px">
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <div class="grade2">
      <div><label class="c" for="l">Login (e-mail)</label>
        <input id="l" name="login" placeholder="nome.sobrenome@questores.com.br" required></div>
      <div><label class="c" for="n">Nome</label><input id="n" name="nome" placeholder="Nome Sobrenome"></div>
      <div><label class="c" for="pf">Perfil</label><select id="pf" name="perfil">
        {% for k, p in perfis.items() %}<option value="{{ k }}">{{ p.nome }}</option>{% endfor %}
      </select></div>
      <div><button class="p" type="submit">Criar usuário</button></div>
    </div>
  </form>
  <p class="hint">A senha nunca aparece aqui, nem para você. Ao criar, o sistema mostra
    uma senha provisória uma única vez — a pessoa troca no primeiro acesso.</p>
</div></section>

<section><header><span class="passo">2</span><h2>Perfis e telas</h2></header>
<p class="leg">Em vez de marcar tela por tela para cada pessoa, o perfil é definido uma
vez e vale para todo mundo que está nele.</p>
<div class="corpo"><div class="perfis">
{% for k, p in perfis.items() %}
  <div class="perfil"><header><h3>{{ p.nome }}</h3>
    <span class="qt">{{ p.quantos }} pessoa{{ "s" if p.quantos != 1 else "" }}</span></header>
    <p class="d">{{ p.descricao }}</p>
    <form method="post" action="/acessos/perfil">
      <input type="hidden" name="csrf" value="{{ csrf }}">
      <input type="hidden" name="chave" value="{{ k }}">
      <div class="menus">
      {% for id, nome, sens in telas %}
        <label><input type="checkbox" name="telas" value="{{ id }}"
          {% if id in p.telas %}checked{% endif %}
          {% if p.gerir %}disabled{% endif %}> {{ nome }}
          {% if sens %}<span class="s">nomes de cliente</span>{% endif %}</label>
      {% endfor %}
      </div>
      {% if p.gerir %}<p class="hint" style="margin:0">O perfil de administração vê tudo,
        por definição. Não dá para tirar telas dele.</p>
      {% else %}<button type="submit">Salvar telas</button>{% endif %}
    </form>
  </div>
{% endfor %}
</div>
<p class="hint">As telas marcadas com <span class="s">nomes de cliente</span> mostram
  empresa, valor de contrato e trechos do que o cliente escreveu no atendimento.</p>
</div></section>

<section><header><span class="passo">3</span><h2>Registro</h2></header>
<p class="leg">Entradas, tentativas erradas e toda mudança de permissão. Como o painel
mostra dado de cliente, poder responder “quem viu isso?” deixa de ser detalhe.</p>
<div class="corpo"><div class="cx"><table class="reg">
<thead><tr><th>Quando</th><th>Quem</th><th>O quê</th></tr></thead><tbody>
{% for r in registro %}<tr><td>{{ r.quando }}</td><td class="q">{{ r.quem }}</td>
<td>{{ r.o_que }}</td></tr>{% endfor %}
</tbody></table></div></div></section>
""").replace("{{ titulo }}", "Acessos")


@app.route("/trocar-senha", methods=["GET", "POST"])
def trocar_senha():
    f = _ficha()
    if not f:
        return redirect("/login")
    if request.method == "GET":
        return render_template_string(TROCAR, erro=None, csrf=_token())
    if not _token_ok():
        return render_template_string(TROCAR, erro="Sessão expirou. Tente de novo.",
                                      csrf=_token()), 400
    nova = request.form.get("nova") or ""
    if nova != (request.form.get("repete") or ""):
        return render_template_string(TROCAR, erro="As duas senhas não são iguais.",
                                      csrf=_token()), 400
    if len(nova) < 10:
        return render_template_string(TROCAR, erro="Use pelo menos 10 caracteres.",
                                      csrf=_token()), 400
    d = acesso.carregar()
    acesso.definir_usuario(d, f["login"], nova, trocar_senha=False)
    acesso.anotar(d, f["login"], "trocou a própria senha")
    acesso.gravar(d)
    return redirect("/")


def _so_admin():
    f = _ficha()
    if not f or not f["gerir"]:
        abort(403)
    return f


def _tela_acessos(aviso=None, erro=None, codigo=200):
    f = _so_admin()
    d = f["d"]
    quantos = {}
    for u in d["usuarios"].values():
        quantos[u.get("perfil")] = quantos.get(u.get("perfil"), 0) + 1
    perfis = {}
    for k, p in d["perfis"].items():
        perfis[k] = dict(p, quantos=quantos.get(k, 0), telas=set(p.get("telas") or []))
    usuarios = [{"login": login, "nome": u.get("nome") or login,
                 "perfil": u.get("perfil"), "ativo": u.get("ativo"),
                 "trocar_senha": u.get("trocar_senha"),
                 "ultimo": (u.get("ultimo_acesso") or "").replace("T", " ")[:16] or None}
                for login, u in sorted(d["usuarios"].items())]
    peso = f"{PAGINA.stat().st_size / 1024 / 1024:.1f} MB" if PAGINA.exists() else "vários MB"
    return render_template_string(
        ACESSOS, usuarios=usuarios, perfis=perfis, telas=acesso.TELAS,
        registro=list(reversed(d.get("registro") or []))[:25], eu=f["login"],
        csrf=_token(), aviso=aviso, erro=erro, peso=peso), codigo


@app.route("/acessos")
def acessos():
    return _tela_acessos()


@app.route("/acessos/usuario", methods=["POST"])
def acessos_usuario():
    f = _so_admin()
    if not _token_ok():
        return _tela_acessos(erro="Sessão expirou. Tente de novo.", codigo=400)
    d = acesso.carregar()
    login = acesso.normalizar_login(request.form.get("login"))
    if login in d["usuarios"]:
        return _tela_acessos(erro=f"{login} já existe.", codigo=400)
    provisoria = acesso.senha_provisoria()
    try:
        acesso.definir_usuario(d, login, provisoria, nome=request.form.get("nome"),
                               perfil=request.form.get("perfil"), trocar_senha=True)
    except ValueError as e:
        return _tela_acessos(erro=str(e), codigo=400)
    acesso.anotar(d, f["login"], f"criou o usuário {login}")
    acesso.gravar(d)
    return _tela_acessos(aviso={
        "titulo": f"Usuário {login} criado",
        "texto": f"Senha provisória: {provisoria} — anote agora, ela não aparece de novo. "
                 "A pessoa troca no primeiro acesso."})


@app.route("/acessos/senha", methods=["POST"])
def acessos_senha():
    f = _so_admin()
    if not _token_ok():
        return _tela_acessos(erro="Sessão expirou. Tente de novo.", codigo=400)
    d = acesso.carregar()
    login = acesso.normalizar_login(request.form.get("login"))
    if login not in d["usuarios"]:
        return _tela_acessos(erro="Usuário não encontrado.", codigo=404)
    provisoria = acesso.senha_provisoria()
    acesso.definir_usuario(d, login, provisoria, trocar_senha=True)
    acesso.anotar(d, f["login"], f"gerou senha provisória para {login}")
    acesso.gravar(d)
    return _tela_acessos(aviso={
        "titulo": f"Nova senha para {login}",
        "texto": f"Senha provisória: {provisoria} — anote agora, ela não aparece de novo."})


@app.route("/acessos/ativo", methods=["POST"])
def acessos_ativo():
    f = _so_admin()
    if not _token_ok():
        return _tela_acessos(erro="Sessão expirou. Tente de novo.", codigo=400)
    d = acesso.carregar()
    login = acesso.normalizar_login(request.form.get("login"))
    if login == f["login"]:
        return _tela_acessos(erro="Não dá para desativar a si mesmo.", codigo=400)
    if login not in d["usuarios"]:
        return _tela_acessos(erro="Usuário não encontrado.", codigo=404)
    ativo = request.form.get("ativo") == "1"
    acesso.definir_usuario(d, login, ativo=ativo)
    acesso.anotar(d, f["login"], ("reativou " if ativo else "desativou ") + login)
    acesso.gravar(d)
    return _tela_acessos()


@app.route("/acessos/perfil-do-usuario", methods=["POST"])
def acessos_perfil_usuario():
    f = _so_admin()
    if not _token_ok():
        return _tela_acessos(erro="Sessão expirou. Tente de novo.", codigo=400)
    d = acesso.carregar()
    login = acesso.normalizar_login(request.form.get("login"))
    perfil = request.form.get("perfil")
    if login not in d["usuarios"]:
        return _tela_acessos(erro="Usuário não encontrado.", codigo=404)
    # o ultimo administrador nao pode se rebaixar: ninguem mais entraria aqui
    admins = [n for n, u in d["usuarios"].items()
              if u.get("ativo") and (d["perfis"].get(u.get("perfil")) or {}).get("gerir")]
    if admins == [login] and not (d["perfis"].get(perfil) or {}).get("gerir"):
        return _tela_acessos(erro="Este é o único administrador ativo. Promova outra "
                                  "pessoa antes de mudar o perfil dele.", codigo=400)
    try:
        acesso.definir_usuario(d, login, perfil=perfil)
    except ValueError as e:
        return _tela_acessos(erro=str(e), codigo=400)
    acesso.anotar(d, f["login"],
                  f"deu o perfil {d['perfis'][perfil]['nome']} para {login}")
    acesso.gravar(d)
    return _tela_acessos()


@app.route("/acessos/perfil", methods=["POST"])
def acessos_perfil():
    f = _so_admin()
    if not _token_ok():
        return _tela_acessos(erro="Sessão expirou. Tente de novo.", codigo=400)
    d = acesso.carregar()
    chave = request.form.get("chave")
    p = d["perfis"].get(chave)
    if not p:
        return _tela_acessos(erro="Perfil não encontrado.", codigo=404)
    if p.get("gerir"):
        return _tela_acessos(erro="O perfil de administração vê tudo.", codigo=400)
    validas = {i for i, _, _ in acesso.TELAS}
    p["telas"] = [t for t in request.form.getlist("telas") if t in validas]
    acesso.anotar(d, f["login"],
                  f"mudou as telas do perfil {p['nome']} para {len(p['telas'])} tela(s)")
    acesso.gravar(d)
    _CACHE.clear()
    return _tela_acessos(aviso={"titulo": f"Perfil {p['nome']} salvo",
                                "texto": f"{len(p['telas'])} tela(s) liberada(s). "
                                         "Vale no próximo carregamento do painel."})


def main() -> None:
    ler = argparse.ArgumentParser(description="Serve o painel CS Questor.")
    ler.add_argument("--porta", type=int, default=PORTA_PADRAO)
    ler.add_argument("--host", default=HOST_PADRAO)
    ler.add_argument("--definir-usuario", metavar="NOME",
                     help="cria ou troca a senha de um usuario e sai")
    args = ler.parse_args()

    if args.definir_usuario:
        senha = getpass.getpass(f"senha para {args.definir_usuario}: ")
        if not senha:
            sys.exit("senha vazia, nada foi gravado")
        if senha != getpass.getpass("repita: "):
            sys.exit("as senhas nao conferem, nada foi gravado")
        definir_usuario(args.definir_usuario, senha)
        print(f"usuario {args.definir_usuario} gravado em {ACESSO}")
        return

    dados = acesso.carregar()
    # grava a migracao de formato, se o arquivo ainda estava no modelo antigo
    acesso.gravar(dados)
    if not dados.get("usuarios"):
        sys.exit("nenhum usuario cadastrado.\n"
                 "  crie um com: python servidor.py --definir-usuario admin")
    app.secret_key = dados["segredo"]
    app.permanent_session_lifetime = timedelta(hours=SESSAO_HORAS)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

    if not PAGINA.exists():
        print("AVISO: dashboard/index.html ainda nao existe.")
        print("       Gere com: python src/painel.py")

    aberto = args.host not in ("127.0.0.1", "localhost")
    print(f"painel CS Questor em http://{args.host if aberto else 'localhost'}:{args.porta}/")
    print(f"  {len(dados['usuarios'])} usuario(s) cadastrado(s), sessao de {SESSAO_HORAS}h")
    if aberto:
        print("  escutando na rede. A pagina tem dado real de cliente atras do login.")
    app.run(host=args.host, port=args.porta, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

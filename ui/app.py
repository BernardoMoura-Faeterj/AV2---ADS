"""Interface grafica (Tkinter) do FocaAI - RNF05: configurar uma sessao em poucos cliques."""
import queue
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

import psutil

from models.modelos import (AGENDADA, ATIVA, TOLERANCIA_MAX, TOLERANCIA_MIN, TOLERANCIA_PADRAO_MIN,
                            Configuracao, eh_protegido, normalizar_processo)
from models.usuario import ErroRegra
from services.gerenciador_sessao import ErroValidacao, converter_data
from services.monitor_webcam import AUSENTE, CONTANDO, FOCADO

AZUL, AZUL_CLARO, VERDE, LARANJA, VERMELHO, CINZA = "#1F4E79", "#DCE6F4", "#2E7D32", "#E08A00", "#C62828", "#666666"
CATEGORIAS = ["Jogos", "Redes sociais", "Entretenimento", "Vídeo", "Outros"]
TIPOS_AVISO = ["Sonoro e visual", "Sonoro", "Visual"]
STATUS_TXT = {"agendada": "Agendada", "ativa": "Ativa", "finalizada": "Finalizada",
              "interrompida": "Interrompida", "perdida": "Não realizada"}


def fmt_hms(seg: int) -> str:
    h, r = divmod(max(0, int(seg)), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def data_br(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")


class FocaAIApp(tk.Tk):
    def __init__(self, banco, gerenciador, usuario):
        super().__init__()
        self.banco, self.ger, self.usuario = banco, gerenciador, usuario
        self.title("FocaAI – Sistema Anti-Procrastinação")
        self.geometry("920x640")
        self.minsize(820, 560)
        self._alerta = None
        self._som_ativo = False
        self._sessao_editando = None
        self._estilo()
        self._montar()
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.ger.iniciar_agendador()
        self.atualizar_tudo()
        self.after(500, self._tick)

    # ------------------------------------------------------------------ estilo
    def _estilo(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10, "bold"))
        st.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
        st.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background=AZUL_CLARO)
        st.configure("Titulo.TLabel", font=("Segoe UI", 16, "bold"), foreground=AZUL)
        st.configure("Sub.TLabel", font=("Segoe UI", 10), foreground=CINZA)
        st.configure("Acao.TButton", font=("Segoe UI", 10, "bold"), padding=8)
        st.configure("Perigo.TButton", font=("Segoe UI", 10, "bold"), padding=8, foreground=VERMELHO)

    def _montar(self):
        topo = tk.Frame(self, bg=AZUL)
        topo.pack(fill="x")
        tk.Label(topo, text="FocaAI", bg=AZUL, fg="white", font=("Segoe UI", 20, "bold")).pack(side="left", padx=16, pady=8)
        tk.Label(topo, text="mantenha o foco, sem desculpas", bg=AZUL, fg="#BFD3EA",
                 font=("Segoe UI", 10)).pack(side="left", pady=8)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)
        self.aba_painel, self.aba_sessoes = ttk.Frame(self.nb), ttk.Frame(self.nb)
        self.aba_apps, self.aba_config, self.aba_hist = (ttk.Frame(self.nb) for _ in range(3))
        for aba, nome in ((self.aba_painel, "Painel"), (self.aba_sessoes, "Sessões"),
                          (self.aba_apps, "Aplicativos bloqueados"), (self.aba_config, "Configurações"),
                          (self.aba_hist, "Histórico")):
            self.nb.add(aba, text=nome)
        self._montar_painel()
        self._montar_sessoes()
        self._montar_apps()
        self._montar_config()
        self._montar_historico()
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.atualizar_tudo())

    # ------------------------------------------------------------------ painel
    def _montar_painel(self):
        f = self.aba_painel
        ttk.Label(f, text="Painel da sessão", style="Titulo.TLabel").pack(anchor="w", padx=16, pady=(14, 4))
        bg = ttk.Style().lookup("TFrame", "background")
        self.lbl_sessao = tk.Label(f, text="", font=("Segoe UI", 13), anchor="w", bg=bg)
        self.lbl_sessao.pack(fill="x", padx=16)
        self.lbl_tempo = tk.Label(f, text="--:--:--", font=("Segoe UI", 44, "bold"), fg=AZUL, bg=bg)
        self.lbl_tempo.pack(pady=(6, 0))
        self.lbl_foco = tk.Label(f, text="", font=("Segoe UI", 14, "bold"), bg=bg)
        self.lbl_foco.pack(pady=(0, 6))
        stats = ttk.Frame(f)
        stats.pack(pady=4)
        self.lbl_bloq, self.lbl_aus = tk.StringVar(value="0"), tk.StringVar(value="0")
        for i, (txt, var) in enumerate((("Apps bloqueados", self.lbl_bloq), ("Ausências", self.lbl_aus))):
            box = tk.Frame(stats, bg=AZUL_CLARO, padx=24, pady=8)
            box.grid(row=0, column=i, padx=10)
            tk.Label(box, textvariable=var, bg=AZUL_CLARO, fg=AZUL, font=("Segoe UI", 22, "bold")).pack()
            tk.Label(box, text=txt, bg=AZUL_CLARO, font=("Segoe UI", 9)).pack()
        bt = ttk.Frame(f)
        bt.pack(pady=10)
        self.btn_iniciar = ttk.Button(bt, text="▶ Iniciar sessão selecionada", style="Acao.TButton",
                                      command=self.iniciar_selecionada)
        self.btn_iniciar.grid(row=0, column=0, padx=6)
        ttk.Label(bt, text="ou sessão rápida de").grid(row=0, column=1, padx=(14, 4))
        self.var_rapida = tk.IntVar(value=25)
        ttk.Spinbox(bt, from_=1, to=240, width=4, textvariable=self.var_rapida).grid(row=0, column=2)
        ttk.Label(bt, text="min").grid(row=0, column=3, padx=(2, 6))
        self.btn_rapida = ttk.Button(bt, text="Iniciar agora", style="Acao.TButton", command=self.sessao_rapida)
        self.btn_rapida.grid(row=0, column=4, padx=4)
        self.btn_encerrar = ttk.Button(bt, text="■ Encerrar sessão", style="Perigo.TButton", command=self.encerrar)
        self.btn_encerrar.grid(row=0, column=5, padx=(18, 0))
        ttk.Label(f, text="Registro de eventos", style="Sub.TLabel").pack(anchor="w", padx=16)
        quadro = ttk.Frame(f)
        quadro.pack(fill="both", expand=True, padx=16, pady=(2, 12))
        self.log = tk.Text(quadro, height=8, state="disabled", font=("Consolas", 10), bg="#F7F9FC", relief="flat")
        sb = ttk.Scrollbar(quadro, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def registrar_log(self, texto):
        self.log.configure(state="normal")
        self.log.insert("end", f"[{datetime.now():%H:%M:%S}] {texto}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------------ sessoes (UC01)
    def _montar_sessoes(self):
        f = self.aba_sessoes
        ttk.Label(f, text="Sessões de foco", style="Titulo.TLabel").pack(anchor="w", padx=16, pady=(14, 6))
        form = ttk.LabelFrame(f, text="Dados da sessão")
        form.pack(fill="x", padx=16, pady=4)
        self.v_nome, self.v_data = tk.StringVar(), tk.StringVar(value=datetime.now().strftime("%d/%m/%Y"))
        self.v_ini, self.v_fim = tk.StringVar(value="13:00"), tk.StringVar(value="16:00")
        for col, (rot, var, larg) in enumerate((("Nome", self.v_nome, 24), ("Data (DD/MM/AAAA)", self.v_data, 14),
                                               ("Início (HH:MM)", self.v_ini, 8), ("Fim (HH:MM)", self.v_fim, 8))):
            ttk.Label(form, text=rot).grid(row=0, column=col, sticky="w", padx=8, pady=(6, 0))
            ttk.Entry(form, textvariable=var, width=larg).grid(row=1, column=col, padx=8, pady=(0, 8), sticky="w")
        bt = ttk.Frame(f)
        bt.pack(fill="x", padx=16, pady=4)
        for txt, cmd in (("Adicionar", self.adicionar_sessao), ("Salvar edição", self.salvar_sessao),
                         ("Excluir", self.excluir_sessao), ("Limpar", self._limpar_form_sessao)):
            ttk.Button(bt, text=txt, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Button(bt, text="▶ Iniciar agora", style="Acao.TButton", command=self.iniciar_selecionada).pack(side="right")
        cols = ("nome", "data", "inicio", "fim", "status")
        self.tv_sessoes = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("nome", "Nome", 280), ("data", "Data", 110), ("inicio", "Início", 80),
                        ("fim", "Fim", 80), ("status", "Status", 130)):
            self.tv_sessoes.heading(c, text=t)
            self.tv_sessoes.column(c, width=w, anchor="w")
        self.tv_sessoes.pack(fill="both", expand=True, padx=16, pady=(6, 14))
        self.tv_sessoes.bind("<<TreeviewSelect>>", self._carregar_sessao_no_form)

    def _limpar_form_sessao(self):
        self._sessao_editando = None
        self.v_nome.set("")
        self.tv_sessoes.selection_remove(self.tv_sessoes.selection())

    def _carregar_sessao_no_form(self, _e=None):
        sel = self.tv_sessoes.selection()
        if not sel:
            return
        s = self.banco.obter_sessao(int(sel[0]))
        if s:
            self._sessao_editando = s.id
            self.v_nome.set(s.nome); self.v_data.set(data_br(s.data))
            self.v_ini.set(s.horario_inicio); self.v_fim.set(s.horario_fim)

    def adicionar_sessao(self):
        try:
            self.usuario.cadastrar_sessao(self.ger, self.v_nome.get(), self.v_data.get(), self.v_ini.get(), self.v_fim.get())
        except ErroValidacao as e:
            return messagebox.showerror("Sessão inválida", str(e))
        self._limpar_form_sessao()
        self.atualizar_tudo()

    def salvar_sessao(self):
        if self._sessao_editando is None:
            return messagebox.showinfo("Editar", "Selecione uma sessão na lista para editá-la.")
        try:
            self.ger.editar_sessao(self._sessao_editando, self.v_nome.get(), self.v_data.get(),
                                   self.v_ini.get(), self.v_fim.get())
        except ErroValidacao as e:
            return messagebox.showerror("Sessão inválida", str(e))
        self.atualizar_tudo()

    def excluir_sessao(self):
        if self._sessao_editando is None:
            return messagebox.showinfo("Excluir", "Selecione uma sessão na lista.")
        if not messagebox.askyesno("Excluir sessão", "Deseja realmente excluir esta sessão?"):   # A1 do UC01
            return
        try:
            self.ger.excluir_sessao(self._sessao_editando)
        except ErroValidacao as e:
            return messagebox.showerror("Não foi possível excluir", str(e))
        self._limpar_form_sessao()
        self.atualizar_tudo()

    def _sessao_selecionada_id(self):
        sel = self.tv_sessoes.selection()
        if sel:
            return int(sel[0])
        abertas = [s for s in self.banco.listar_sessoes() if s.status == AGENDADA]
        return abertas[0].id if abertas else None

    def iniciar_selecionada(self):
        sid = self._sessao_selecionada_id()
        if sid is None:
            return messagebox.showinfo("Iniciar sessão", "Cadastre uma sessão na aba Sessões primeiro.")
        try:
            self.ger.iniciar_sessao(sid)
        except ErroValidacao as e:
            return messagebox.showerror("Não foi possível iniciar", str(e))
        self.nb.select(self.aba_painel)

    def sessao_rapida(self):
        try:
            self.ger.criar_sessao_rapida(int(self.var_rapida.get()))
        except (ErroValidacao, tk.TclError, ValueError) as e:
            return messagebox.showerror("Sessão rápida", str(e) if isinstance(e, ErroValidacao) else "Informe os minutos.")
        self.nb.select(self.aba_painel)

    def encerrar(self):
        if self.ger.sessao_ativa is None:
            return
        if messagebox.askyesno("Encerrar sessão", "Encerrar a sessão antes do horário?\n"
                               "O encerramento antecipado ficará registrado no histórico."):     # RN08
            self.ger.encerrar_antecipado()

    # ------------------------------------------------------------------ apps bloqueados (UC02)
    def _montar_apps(self):
        f = self.aba_apps
        ttk.Label(f, text="Aplicativos bloqueados", style="Titulo.TLabel").pack(anchor="w", padx=16, pady=(14, 2))
        ttk.Label(f, text="Durante uma sessão ativa, estes programas são fechados assim que abrirem.",
                  style="Sub.TLabel").pack(anchor="w", padx=16)
        form = ttk.Frame(f)
        form.pack(fill="x", padx=16, pady=8)
        self.v_app, self.v_cat = tk.StringVar(), tk.StringVar(value=CATEGORIAS[0])
        ttk.Label(form, text="Executável (ex.: steam.exe)").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.v_app, width=28).grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Label(form, text="Categoria").grid(row=0, column=1, sticky="w")
        ttk.Combobox(form, textvariable=self.v_cat, values=CATEGORIAS, width=16).grid(row=1, column=1, padx=(0, 8))
        ttk.Button(form, text="Adicionar", command=self.adicionar_app).grid(row=1, column=2, padx=4)
        ttk.Button(form, text="Escolher dos processos abertos…", command=self.escolher_processo).grid(row=1, column=3, padx=4)
        ttk.Button(form, text="Remover selecionado", command=self.remover_app).grid(row=1, column=4, padx=4)
        self.tv_apps = ttk.Treeview(f, columns=("nome", "cat"), show="headings", selectmode="browse")
        self.tv_apps.heading("nome", text="Executável"); self.tv_apps.heading("cat", text="Categoria")
        self.tv_apps.column("nome", width=360); self.tv_apps.column("cat", width=200)
        self.tv_apps.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    def adicionar_app(self):
        try:
            self.usuario.adicionar_aplicativo(self.v_app.get(), self.v_cat.get() or "Outros")
        except ErroRegra as e:
            return messagebox.showwarning("Aplicativo não adicionado", str(e))
        self.v_app.set("")
        self.atualizar_apps()

    def remover_app(self):
        sel = self.tv_apps.selection()
        if sel:
            self.usuario.remover_aplicativo(int(sel[0]))
            self.atualizar_apps()

    def escolher_processo(self):
        """Passo 4 do UC02: o sistema consulta o SO e exibe os aplicativos disponiveis."""
        nomes = sorted({p.info["name"] for p in psutil.process_iter(["name"])
                        if p.info.get("name") and not eh_protegido(p.info["name"])}, key=str.lower)
        dlg = tk.Toplevel(self)
        dlg.title("Processos em execução"); dlg.geometry("340x420"); dlg.transient(self); dlg.grab_set()
        lb = tk.Listbox(dlg, font=("Segoe UI", 10))
        lb.pack(fill="both", expand=True, padx=10, pady=10)
        for n in nomes:
            lb.insert("end", n)
        def ok(_e=None):
            if lb.curselection():
                self.v_app.set(lb.get(lb.curselection()[0]))
            dlg.destroy()
        lb.bind("<Double-Button-1>", ok)
        ttk.Button(dlg, text="Selecionar", command=ok).pack(pady=(0, 10))

    def atualizar_apps(self):
        self.tv_apps.delete(*self.tv_apps.get_children())
        for a in self.banco.listar_apps():
            self.tv_apps.insert("", "end", iid=str(a.id), values=(a.nome_processo, a.categoria))

    # ------------------------------------------------------------------ configuracoes (UC03)
    def _montar_config(self):
        f = self.aba_config
        ttk.Label(f, text="Configurações", style="Titulo.TLabel").pack(anchor="w", padx=16, pady=(14, 8))
        box = ttk.LabelFrame(f, text="Monitoramento de presença")
        box.pack(fill="x", padx=16, pady=4)
        self.v_tol, self.v_aviso = tk.IntVar(value=TOLERANCIA_PADRAO_MIN), tk.StringVar(value=TIPOS_AVISO[0])
        self.v_cam, self.v_demo = tk.BooleanVar(value=True), tk.BooleanVar(value=False)
        ttk.Label(box, text=f"Tolerância de ausência (minutos, {TOLERANCIA_MIN} a {TOLERANCIA_MAX})").grid(
            row=0, column=0, sticky="w", padx=10, pady=8)
        ttk.Spinbox(box, from_=TOLERANCIA_MIN, to=TOLERANCIA_MAX, width=5, textvariable=self.v_tol).grid(row=0, column=1, sticky="w")
        ttk.Label(box, text="Tipo de aviso").grid(row=1, column=0, sticky="w", padx=10, pady=8)
        ttk.Combobox(box, textvariable=self.v_aviso, values=TIPOS_AVISO, state="readonly", width=18).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(box, variable=self.v_cam, text="Permito o uso da câmera para detectar minha presença e atenção").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 0))
        ttk.Label(box, text="As imagens são analisadas só na memória e nunca são gravadas nem enviadas.",
                  style="Sub.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", padx=32, pady=(0, 8))
        ttk.Checkbutton(box, variable=self.v_demo, text="Modo demonstração (a tolerância passa a contar em SEGUNDOS)").grid(
            row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))
        bt = ttk.Frame(f)
        bt.pack(anchor="w", padx=16, pady=8)
        ttk.Button(bt, text="Salvar", style="Acao.TButton", command=self.salvar_config).pack(side="left", padx=(0, 8))
        ttk.Button(bt, text="Restaurar padrão", command=self.restaurar_config).pack(side="left")
        ttk.Label(f, text="As alterações valem a partir da próxima sessão.", style="Sub.TLabel").pack(anchor="w", padx=16)

    def atualizar_config(self):
        c = self.banco.obter_config()
        self.v_tol.set(c.tempo_tolerancia_minutos)
        self.v_cam.set(c.camera_ativa); self.v_demo.set(c.modo_demo)
        self.v_aviso.set(TIPOS_AVISO[0] if c.aviso_sonoro and c.aviso_visual else
                         TIPOS_AVISO[1] if c.aviso_sonoro else TIPOS_AVISO[2])

    def salvar_config(self):
        try:
            minutos = int(self.v_tol.get())
        except (tk.TclError, ValueError):
            return messagebox.showerror("Configurações", "Informe a tolerância em números inteiros.")
        try:
            self.usuario.configurar_tolerancia(minutos)           # valida RN03
        except ErroRegra as e:
            self.atualizar_config()                               # E1: mantem o valor anterior
            return messagebox.showerror("Tolerância inválida", str(e))
        c = self.banco.obter_config()
        tipo = self.v_aviso.get()
        c.aviso_sonoro, c.aviso_visual = tipo in (TIPOS_AVISO[0], TIPOS_AVISO[1]), tipo in (TIPOS_AVISO[0], TIPOS_AVISO[2])
        c.camera_ativa, c.modo_demo = self.v_cam.get(), self.v_demo.get()
        self.banco.salvar_config(c)
        messagebox.showinfo("Configurações", "Configurações salvas.")

    def restaurar_config(self):
        self.banco.salvar_config(Configuracao())                   # A1: tolerancia volta para 5 min
        self.atualizar_config()

    # ------------------------------------------------------------------ historico (UC10)
    def _montar_historico(self):
        f = self.aba_hist
        ttk.Label(f, text="Histórico de sessões", style="Titulo.TLabel").pack(anchor="w", padx=16, pady=(14, 6))
        filtro = ttk.Frame(f)
        filtro.pack(fill="x", padx=16)
        self.v_de, self.v_ate = tk.StringVar(), tk.StringVar()
        ttk.Label(filtro, text="De").pack(side="left"); ttk.Entry(filtro, textvariable=self.v_de, width=12).pack(side="left", padx=4)
        ttk.Label(filtro, text="Até").pack(side="left"); ttk.Entry(filtro, textvariable=self.v_ate, width=12).pack(side="left", padx=4)
        ttk.Button(filtro, text="Filtrar", command=self.atualizar_historico).pack(side="left", padx=4)
        ttk.Button(filtro, text="Limpar filtro", command=lambda: (self.v_de.set(""), self.v_ate.set(""), self.atualizar_historico())).pack(side="left")
        ttk.Label(filtro, text="(datas em DD/MM/AAAA)", style="Sub.TLabel").pack(side="left", padx=8)
        cols = ("data", "nome", "dur", "foco", "bloq", "aus", "status")
        self.tv_hist = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("data", "Data", 90), ("nome", "Sessão", 230), ("dur", "Duração", 90), ("foco", "% foco", 70),
                        ("bloq", "Bloqueios", 80), ("aus", "Ausências", 80), ("status", "Status", 110)):
            self.tv_hist.heading(c, text=t); self.tv_hist.column(c, width=w, anchor="w")
        self.tv_hist.pack(fill="both", expand=True, padx=16, pady=(8, 4))
        self.tv_hist.bind("<Double-Button-1>", self.detalhes_historico)
        self.lbl_vazio = ttk.Label(f, text="", style="Sub.TLabel")
        self.lbl_vazio.pack(pady=(0, 10))

    def atualizar_historico(self):
        try:
            de = converter_data(self.v_de.get()) if self.v_de.get().strip() else None
            ate = converter_data(self.v_ate.get()) if self.v_ate.get().strip() else None
        except ErroValidacao as e:
            return messagebox.showerror("Filtro", str(e))
        self.tv_hist.delete(*self.tv_hist.get_children())
        itens = self.usuario.consultar_historico(de, ate)
        for s, r in itens:
            self.tv_hist.insert("", "end", iid=str(s.id), values=(
                data_br(s.data), s.nome, fmt_hms(r.tempo_total_seg), f"{r.percentual_foco}%",
                r.numero_bloqueios, r.numero_ausencias, STATUS_TXT.get(s.status, s.status)))
        self.lbl_vazio.configure(text="" if itens else "Nenhuma sessão registrada")             # E1 do UC10

    def detalhes_historico(self, _e=None):
        sel = self.tv_hist.selection()
        if not sel:
            return
        sid = int(sel[0])
        s = self.banco.obter_sessao(sid)
        linhas = [f"{s.nome} – {data_br(s.data)} ({s.horario_inicio} às {s.horario_fim})", "", "Aplicativos bloqueados:"]
        tent = self.banco.listar_tentativas(sid)
        linhas += [f"  {t.data_hora[11:]}  {t.nome_processo}" + ("" if t.sucesso else "  (falha ao encerrar)") for t in tent] or ["  nenhum"]
        linhas += ["", "Ausências / avisos emitidos:"]
        oc = self.banco.listar_ocorrencias(sid)
        linhas += [f"  {o.data_hora[11:]}  ausente por {fmt_hms(o.duracao_ausencia)}" for o in oc] or ["  nenhuma"]
        dlg = tk.Toplevel(self); dlg.title("Detalhes da sessão"); dlg.geometry("480x380"); dlg.transient(self)
        t = tk.Text(dlg, font=("Consolas", 10), padx=10, pady=10); t.pack(fill="both", expand=True)
        t.insert("1.0", "\n".join(linhas)); t.configure(state="disabled")

    # ------------------------------------------------------------------ eventos, alertas, resumo
    def _tick(self):
        try:
            while True:
                tipo, dados = self.ger.eventos.get_nowait()
                self._tratar_evento(tipo, dados)
        except queue.Empty:
            pass
        self._atualizar_painel()
        self.after(500, self._tick)

    def _tratar_evento(self, tipo, d):
        if "texto" in d:
            self.registrar_log(d["texto"])
        if tipo == "bloqueio" or tipo == "bloqueio_falha":
            self._toast(d["texto"])
        elif tipo == "aviso":
            self._abrir_alerta(d.get("visual", True), d.get("sonoro", True))
        elif tipo == "aviso_fim":
            self._fechar_alerta()
        elif tipo == "sessao_iniciada":
            self.registrar_log(f"Sessão '{d['sessao'].nome}' iniciada.")
            self.atualizar_tudo()
        elif tipo == "sessao_finalizada":
            self._fechar_alerta()
            self.registrar_log(f"Sessão '{d['sessao'].nome}' {STATUS_TXT[d['sessao'].status].lower()}.")
            self.atualizar_tudo()
            self._mostrar_resumo(d["sessao"], d["resumo"])
        elif tipo == "camera_indisponivel":
            self._toast(d["texto"])

    def _atualizar_painel(self):
        s = self.ger.sessao_ativa
        ativo = s is not None
        self.btn_encerrar.state(["!disabled"] if ativo else ["disabled"])
        for b in (self.btn_iniciar, self.btn_rapida):
            b.state(["disabled"] if ativo else ["!disabled"])
        if not ativo:
            proxima = next((x for x in self.banco.listar_sessoes() if x.status == AGENDADA), None)
            self.lbl_sessao.configure(text="Nenhuma sessão ativa." + (
                f"  Próxima: {proxima.nome} – {data_br(proxima.data)} {proxima.horario_inicio}" if proxima else ""))
            self.lbl_tempo.configure(text="--:--:--", fg=CINZA)
            self.lbl_foco.configure(text="")
            return
        self.lbl_sessao.configure(text=f"Sessão ativa: {s.nome}  ({s.horario_inicio} às {s.horario_fim})")
        self.lbl_tempo.configure(text=fmt_hms(self.ger.segundos_restantes()), fg=AZUL)
        estado, contagem = self.ger.estado_foco()
        if estado is None:
            self.lbl_foco.configure(text="Somente bloqueio de aplicativos (câmera desligada)", fg=CINZA)
        elif estado == FOCADO:
            self.lbl_foco.configure(text="● Focado", fg=VERDE)
        elif estado == CONTANDO:
            self.lbl_foco.configure(text=f"● Ausência detectada – aviso em {fmt_hms(contagem)[3:]}", fg=LARANJA)
        elif estado == AUSENTE:
            self.lbl_foco.configure(text="● Ausente / desatento", fg=VERMELHO)
        b, a = self.ger.contadores()
        self.lbl_bloq.set(str(b)); self.lbl_aus.set(str(a))

    def _toast(self, texto):
        t = tk.Toplevel(self)
        t.overrideredirect(True); t.attributes("-topmost", True)
        tk.Label(t, text=texto, bg="#333333", fg="white", font=("Segoe UI", 10), padx=14, pady=10, wraplength=340).pack()
        t.update_idletasks()
        x = self.winfo_screenwidth() - t.winfo_width() - 20
        y = self.winfo_screenheight() - t.winfo_height() - 70
        t.geometry(f"+{x}+{y}")
        t.after(3500, t.destroy)

    def _abrir_alerta(self, visual, sonoro):
        self._fechar_alerta()
        if visual:
            a = tk.Toplevel(self)
            a.title("FocaAI – Volte ao foco!"); a.configure(bg=VERMELHO); a.attributes("-topmost", True)
            a.geometry(f"460x220+{(self.winfo_screenwidth()-460)//2}+{(self.winfo_screenheight()-220)//2}")
            tk.Label(a, text="⚠ Volte ao foco!", bg=VERMELHO, fg="white", font=("Segoe UI", 26, "bold")).pack(pady=(28, 4))
            tk.Label(a, text="Você ficou ausente além do tempo de tolerância.", bg=VERMELHO, fg="white",
                     font=("Segoe UI", 11)).pack()
            ttk.Button(a, text="Dispensar aviso", command=self._dispensar).pack(pady=18)
            a.protocol("WM_DELETE_WINDOW", self._dispensar)
            self._alerta = a
        if sonoro:
            self._som_ativo = True
            self._tocar_som()

    def _tocar_som(self):
        if not self._som_ativo:
            return
        try:
            import winsound
            winsound.Beep(1000, 250)
        except Exception:
            self.bell()
        self.after(1500, self._tocar_som)

    def _dispensar(self):
        if self.ger.monitor_cam:
            self.ger.monitor_cam.dispensar_aviso()
        self._fechar_alerta()

    def _fechar_alerta(self):
        self._som_ativo = False
        if self._alerta is not None:
            try:
                self._alerta.destroy()
            except tk.TclError:
                pass
            self._alerta = None

    def _mostrar_resumo(self, s, r):
        dlg = tk.Toplevel(self)
        dlg.title("Resumo da sessão"); dlg.transient(self); dlg.geometry("400x330"); dlg.grab_set()
        tk.Label(dlg, text="Resumo da sessão", font=("Segoe UI", 16, "bold"), fg=AZUL).pack(pady=(16, 2))
        tk.Label(dlg, text=f"{s.nome} – {STATUS_TXT[s.status]}", font=("Segoe UI", 10), fg=CINZA).pack()
        tk.Label(dlg, text=f"{r.percentual_foco}% de foco", font=("Segoe UI", 28, "bold"),
                 fg=VERDE if r.percentual_foco >= 80 else LARANJA).pack(pady=8)
        tk.Label(dlg, text=r.gerar_relatorio(), font=("Segoe UI", 11), justify="left").pack()
        ttk.Button(dlg, text="Fechar", command=dlg.destroy).pack(pady=16)

    # ------------------------------------------------------------------ geral
    def atualizar_tudo(self):
        sel = self.tv_sessoes.selection()
        self.tv_sessoes.delete(*self.tv_sessoes.get_children())
        for s in self.banco.listar_sessoes():
            self.tv_sessoes.insert("", "end", iid=str(s.id), values=(
                s.nome, data_br(s.data), s.horario_inicio, s.horario_fim, STATUS_TXT.get(s.status, s.status)))
        if sel and self.tv_sessoes.exists(sel[0]):
            self.tv_sessoes.selection_set(sel[0])
        self.atualizar_apps()
        self.atualizar_config()
        self.atualizar_historico()

    def _fechar(self):
        if self.ger.sessao_ativa is not None:
            if not messagebox.askyesno("Sessão ativa", "Há uma sessão em andamento. Encerrar a sessão e sair?"):
                return
            self.ger.encerrar_antecipado()
        self.ger.parar_agendador()
        self._fechar_alerta()
        self.banco.fechar()
        self.destroy()

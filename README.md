# FocaAI – Sistema Anti-Procrastinação (RAD Python)

Aplicação desktop em Python/Tkinter que ajuda o usuário a manter o foco: cadastra sessões de estudo/trabalho,
**fecha automaticamente aplicativos bloqueados** (jogos, redes sociais...) durante a sessão e usa a **webcam**
para detectar ausência/desatenção, com contagem de tolerância e aviso sonoro/visual.

## Como executar (Windows 10/11, Python 3.10+)
```
pip install -r requirements.txt
python main.py
```
O banco de dados `focaai.db` (SQLite) é criado automaticamente na primeira execução.

## Demonstração rápida
1. Aba **Configurações** → marque *Modo demonstração* (tolerância conta em segundos) e salve (ex.: tolerância 5 = 5 s).
2. Aba **Aplicativos bloqueados** → adicione, por exemplo, `notepad.exe` (ou use "Escolher dos processos abertos").
3. Aba **Painel** → *Iniciar agora* (sessão rápida). Abra o Bloco de Notas: ele é fechado em até 2 s.
4. Saia da frente da câmera: após a tolerância, aparecem o aviso visual e o sonoro. Volte: o aviso é encerrado.
5. *Encerrar sessão* → resumo (tempo total, tempo focado, bloqueios, ausências) e registro na aba **Histórico**.

## Estrutura (espelha o Diagrama de Classes da AV1)
```
main.py                      ponto de entrada
models/modelos.py            SessaoFoco, AplicativoBloqueado, Configuracao, TentativaAbertura,
                             OcorrenciaDistracao, ResumoSessao + constantes e RN07
models/usuario.py            Usuario (fachada: aplicativos, tolerância, histórico)
database/db.py               persistência SQLite (RNF06)
services/monitor_processos.py  MonitorProcessos  (UC05)
services/monitor_webcam.py     MonitorWebcam     (UC06, UC07) – imagens só em memória (RN05)
services/gerenciador_sessao.py ciclo de vida das sessões (UC01, UC04, UC08, UC09)
ui/app.py                    telas: Painel, Sessões, Aplicativos, Configurações, Histórico
tests/test_core.py           13 testes automatizados das regras de negócio
```

## Testes
```
python -m unittest discover -s tests -v
```
(o teste de bloqueio de processos usa o comando `sleep`, disponível em Linux/macOS; no Windows esse único teste
pode ser ignorado ou adaptado para `notepad.exe`.)

## Limitações conhecidas
- A atenção é estimada pela detecção de rosto frontal (OpenCV/Haar): rosto virado ou ausente = desatento.
- Sessões não atravessam a meia-noite (horário de fim deve ser posterior ao de início, no mesmo dia).
- Alterações em Configurações valem a partir da próxima sessão.

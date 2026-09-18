# Experimental: Image Click (Hyprland)

PoC de "achar uma imagem na tela e clicar nela" — a base de um futuro modo
de macros por reconhecimento visual no LinuxTask.

**Não é referenciado pela aplicação.** Nada em `src/`, `tools/` ou no CI
importa ou executa estes arquivos; o diretório `experimental/` existe só
para referência (mesmo tratamento dos PoCs de `libei/`).

## Como funciona

```
grim ──PNG──> numpy (NCC via FFT + imagens integrais) ──(x, y)──>
HyprlandDriver.move_cursor() ──> clique via uinput (evdev)
```

- **Captura**: `grim` grava um PNG em memória; decodificado com PIL.
- **Matching**: NCC (correlação cruzada normalizada) por canal RGB, via
  `numpy.fft` — sem OpenCV, sem SciPy, sem sliding windows materializadas.
  Normalização da variância local com imagens integrais, então áreas
  planas da tela não geram falso-positivo.
- **Ação**: move o cursor com o driver real de `src/drivers/hyprland.py`
  (herda clamp, dispatcher novo do Hyprland 0.55+ com fallback legado) e
  clica com um dispositivo virtual uinput.

## Uso (dentro de uma sessão Hyprland)

### Teste por partes (recomendado)

Três passos independentes — se um falha, você sabe exatamente onde:

```bash
# PASSO 0 — capturar um template: abre uma seleção com o mouse (slurp)
# e salva o recorte como PNG. Arraste sobre o botão/ícone alvo:
python3 grab_template.py                   # salva em template.png
python3 grab_template.py botao.png         # ou com nome próprio

# PASSO 1 — só o clique (uinput), sem mover nem capturar nada.
# Ponha o cursor sobre um lugar inofensivo (ex.: área vazia do desktop)
# antes de rodar. Com --dry-run ele só valida o dispositivo:
python3 click_test.py --dry-run
python3 click_test.py --count 3            # 3 cliques onde o cursor está
python3 click_test.py --button right       # botão direito

# PASSO 2 — só a busca de imagem, sem mexer em nada.
python3 find.py --template botao.png       # reporta "ACHOU: x=.. y=.."

# PASSO 3 — pipeline completo (buscar + mover + clicar):
python3 image_click.py --template botao.png --click
```

### Outras opções

```bash
# Achar e mover o cursor até a imagem (sem clicar)
python3 image_click.py --template botao.png

# Opções úteis
python3 image_click.py --template botao.png --click \
    --confidence 0.9 \
    --output DP-1 --scale 2 \
    --timeout 5 --poll 0.1

# Self-test headless do matcher (sem display, sem grim)
python3 image_click.py --selftest
```

O `--template` é um **recorte PNG da UI alvo** capturado na mesma escala
da sessão (ex.: com `grim -g "<x>,<y> <w>x<h>" arquivo.png`). Em telas
HiDPI, combine `--scale` (grim) com `--template-scale` se o template foi
feito em outra escala de DPI.

## Limitações conhecidas (o que um MVP real precisaria resolver)

- **DPI/escala fracionária** (125%, 150%): template e tela precisam da
  mesma escala — hoje só há reescala manual via `--template-scale`.
- **Temas/estados de UI**: botão desabilitado, hover, tema claro/escuro
  mudam os pixels; NCC cai e pode exigir `--confidence` menor.
- **Multi-monitor**: `grim` sem `--output` captura tudo; o matching roda
  sobre a imagem inteira (correto, mas mais lento).
- **Sem teste de clique**: o self-test cobre só o matcher; o clique
  injeta eventos reais e exige sessão própria para validar.
- **Performance**: ~O(tela log tela) por canal; se um dia precisar de
  latência menor, OpenCV `matchTemplate` é o próximo passo.

## Status

- **Matcher**: validado headless (self-test: coordenada exata e rejeição
  de template inexistente) **e** em sessão Hyprland real (1920×1080,
  scale 1): match com score 1.000 e desvio de 0 px entre duas capturas.
- **Captura + move_cursor**: validados em sessão real via `hyprctl
  cursorpos` (cursor chegou exatamente no centro do match e foi
  restaurado).
- **Clique (uinput)**: validado em sessão real (click_test + pipeline
  completo com `--click` executados pelo usuário, score 1.000).
- **Pegadinha de grim**: builds recentes não escrevem PNG no stdout sem
  o destino `-` explícito — `grab_screen()` já passa `-` e mantém as
  opções antes dele.

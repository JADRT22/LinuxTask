# Experimental: Color Spin (Hyprland)

## O caminho fácil: assistente

```bash
python3 assistente.py
```

Um comando só. Ele te guia:
1. **Onde é o botão?** — você arrasta um quadradinho em volta dele
2. **Onde o resultado aparece?** — arrasta outro quadradinho
3. **Qual é a cor rara?** — abre a área ampliada e você clica nela

Depois mostra um resumo, salva tudo em `spin_config.json` e começa a
girar. Nas próximas vezes: `python3 assistente.py` → Enter → girando.

Apagar a configuração pra refazer: `rm spin_config.json`.

---

## O caminho manual (script por script)

Loop de clique **até uma cor aparecer** numa região da tela — o caso de
uso "girar clans em jogos de Roblox": clica no botão de girar
repetidamente e para quando a cor rara do resultado aparece.

**Não é referenciado pela aplicação.** Nada em `src/` ou no CI importa
estes arquivos (mesmo tratamento dos demais PoCs em `experimental/`).

## Como funciona

```
loop:
  1. move o cursor ao botão (HyprlandDriver) e clica (uinput)
  2. espera a ROLETA PARAR: compara capturas seguidas da região e só
     segue quando a imagem estabiliza (animação de "passar pelos clans"
     não gera mais falso-positivo — o clan raro que só PASSOU é
     ignorado; se for o resultado de verdade, fica parado e detecta)
  3. numpy conta os pixels dentro da tolerância do RGB alvo
  4. cor >= threshold? para. senão, volta ao passo 1.
```

A tolerância é a distância máxima **por canal** RGB (Chebyshev): `40`
pega qualquer cor "parecida" (ex.: `255,215,0` dourado com tol 40 pega
também `230,200,30`). O `--threshold` é a fração da região que precisa
estar na cor (2% por default) — evita falso-positivo de um pixel solto.

## Uso (dentro de uma sessão Hyprland)

```bash
# 0. (uma vez) capture a região onde o RESULTADO aparece — só pra você
#    ver/consultar depois e escolher a cor:
python3 grab_region.py resultado.png
python3 pick_color.py resultado.png     # clique na cor rara → imprime o RGB

# 1. ache o botão de girar (recorte com ../image_click/grab_template.py):
python3 ../image_click/find.py --template botao_girar.png
#    → anote o "ACHOU: x=... y=..."

# 2. rode o loop:
python3 spin_until_color.py \
    --button-x 1650 --button-y 606 \
    --region "1559,447" "258x253" \
    --color 255,215,0 --tolerance 40 \
    --interval 1.5 --max-spins 100
```

O script mostra a fração de cor detectada a cada giro — use isso para
calibrar `--tolerance` e `--threshold`.

## Status

- **Detecção de cor**: validada em sessão real (positivo 100%,
  negativo 0% numa região homogênea de 100x100).
- **Espera de estabilização**: validada com backends sintéticos
  (animação → estabiliza antes de checar; região que nunca para →
  desiste após `--stable-max` e checa mesmo assim).
- **`capture_region`** (`experimental/capture.py`): validada (grim -g).
- **Loop completo com jogo**: não testado — precisa do Roblox rodando
  (via Sober/Wine); os parâmetros são calibráveis a frio.

## Limitações

- A cor do resultado em jogos pode ter **gradiente/brilho animado**:
  aumente `--tolerance` ou `--stable-diff` nesses casos.
- Se a roleta demorar mais que `--stable-max` (10s) para parar, o giro
  é checado mesmo sem estabilizar (o log avisa).
- Hyprland only (mesmo backport do `image_click`: grim/slurp).
- O clique é sempre via uinput (botão esquerdo).

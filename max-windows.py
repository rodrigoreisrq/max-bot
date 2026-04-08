"""
 MAX — Automacao por Palmas e Voz (Windows)     
                                                         
  Detecta:                                                
   👏  2 palmas (fingerprint espectral)                   
   🎤  Frase de voz customizavel                       
                                                         
  Uso:                                                    
   python jarvis.py              (iniciar)               
   python jarvis.py --calibrar   (recalibrar palmas)     
   Interromper: Ctrl+C                                           

"""

import sys
import subprocess
import json

# ── VERIFICAR DEPENDENCIAS ──────────────────────────────
REQUIRED = {
    "speech_recognition": "SpeechRecognition",
    "sounddevice": "sounddevice",
    "numpy": "numpy",
}

missing = []
for mod, pkg in REQUIRED.items():
    try:
        __import__(mod)
    except ImportError:
        missing.append(pkg)

if missing:
    print(f"\n⚠️  Pacotes em falta: {', '.join(missing)}")
    print(f"   Rode: pip install {' '.join(missing)}")
    print(f"   Ou execute o setup-windows.bat")
    print(f"   Depois rode este script novamente.\n")
    sys.exit(1)

import threading
import time
import webbrowser
import os
import io
import wave
import numpy as np
import sounddevice as sd
import speech_recognition as sr


# 
#                                                            
#   CONFIGURACOES EDITAVÉIS                      
#   Consulte o GUIA-PERSONALIZACAO.pdf para detalhes          
#                                                          
# 


#   Total palmas sequenciais para ativar
CLAP_COUNT            = 2

# Tempo em segundos para carregar as palmas
CLAP_WINDOW           = 2.5

# Amplitude minima para iniciar analise espectral
# Aumente se sons do ambiente (teclado, mesa) estiverem ativando
# Diminua se suas palmas nao sao detectadas
CLAP_AMPLITUDE_THRESH = 0.25

# Similaridade minima com a palma de referencia (0 a 1)
# 0.60 = aceita outros sons, 0.80 = rigido apenas palmas fortes
CLAP_SIMILARITY_THRESH = 0.80

# Intervalo entre palmas evitando de contar uma palma por duas)
CLAP_MIN_INTERVAL     = 0.15

# Configuracoes tecnicas (nao precisa mexer)
CLAP_SAMPLE_RATE      = 44100
CLAP_BLOCK_SIZE       = 2048

# CALIBRACAO 
# Arquivo onde o perfil das suas palmas e salvo
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLAP_PROFILE_FILE = os.path.join(SCRIPT_DIR, "max_clap_profile.json")

# Quantas palmas gravar na calibracao inicial
CALIBRATION_CLAPS = 5

# ── VOZ ─────────────────────────────────────────────────
# Palavra obrigatoria (precisa aparecer na frase)
WAKE_WORDS        = ["max"]

# Pelo menos UMA dessas palavras precisa aparecer tambem
WAKE_CONTEXT      = ["trabalhar", "bora", "trabalho", "vamos"]

# Idioma do reconhecimento de voz
# "pt-BR" = portugues, "en-US" = ingles, "es-ES" = espanhol
VOICE_LANGUAGE     = "pt-BR"

# Configuracoes tecnicas de voz (nao precisa mexer)
VOICE_SAMPLE_RATE  = 16000
VOICE_CHUNK_SEC    = 4
VOICE_SILENCE_THRESH = 0.02

# ── ACOES — O QUE ACONTECE QUANDO ATIVAR ────────────────

# App que abre (caminho completo do executavel)
# Para descobrir o caminho: abra o CMD e digite: where nome_do_app
# Para apps da Microsoft Store: use o formato abaixo
CLAUDE_APP        = r"C:\Users\User\AppData\Local\Programs\Microsoft VS Code\Code.exe"

CLAUDE_APP        = r"C:\Users\User\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd"



# Pasta onde o terminal vai abrir
CLAUDE_CODE_DIR   = r"C:\Users\User\Desktop\projeto-alan"

# Comando que roda no terminal
CLAUDE_CODE_CMD   = "dir /s"

# Musica que toca quando ativar (link direto do YouTube Music, YouTube ou Spotify)
MUSIC_URL         = "https://music.youtube.com/watch?v=-YQ8IbVIwPM&si=p3Y7Ep7eesHOtCOG"

# ── GERAL ───────────────────────────────────────────────
# Tempo entre ativacoes (evita ativar duas vezes seguidas)
COOLDOWN          = 15


# ║  NAO PRECISA EDITAR NADA ABAIXO DESTA LINHA               


# ── STATE ───────────────────────────────────────────────
last_triggered = 0
lock = threading.Lock()
clap_fingerprint = None


def beep(freq=800, dur=100):
    try:
        import winsound
        winsound.Beep(freq, dur)
    except:
        pass


def play_startup_sound():
    beep(600, 150); beep(800, 150); beep(1000, 150); beep(1200, 250)


def play_listening_sound():
    beep(800, 100); beep(1000, 100)


# ── SPECTRAL FINGERPRINT ENGINE ─────────────────────────

def compute_spectral_fingerprint(audio_block, sample_rate):
    windowed = audio_block * np.hanning(len(audio_block))
    fft = np.fft.rfft(windowed)
    magnitude = np.abs(fft)
    freqs = np.fft.rfftfreq(len(audio_block), 1.0 / sample_rate)
    band_edges = np.logspace(np.log10(100), np.log10(min(20000, sample_rate // 2)), 21)
    band_energies = []
    for i in range(len(band_edges) - 1):
        mask = (freqs >= band_edges[i]) & (freqs < band_edges[i + 1])
        if np.any(mask):
            band_energies.append(np.mean(magnitude[mask] ** 2))
        else:
            band_energies.append(0.0)
    fingerprint = np.array(band_energies, dtype=np.float64)
    norm = np.linalg.norm(fingerprint)
    if norm > 0:
        fingerprint = fingerprint / norm
    return fingerprint


def cosine_similarity(a, b):
    dot = np.dot(a, b)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


# ── CALIBRACAO ──────────────────────────────────────────

def calibrate_claps():
    print()
    print("  ╔════════════════════════════════════════════╗")
    print("  ║  👏  CALIBRACAO DE PALMAS                   ║")
    print("  ╠════════════════════════════════════════════╣")
    print(f"  ║  Bata {CALIBRATION_CLAPS} palmas, uma de cada vez.          ║")
    print("  ║  Espere o ✅ antes de bater a proxima.      ║")
    print("  ║  Bata como voce bateria normalmente.        ║")
    print("  ╚════════════════════════════════════════════╝")
    print()

    fingerprints = []
    sr = CLAP_SAMPLE_RATE
    bs = CLAP_BLOCK_SIZE
    min_amp = 0.05

    state = {"detected": False, "fp": None, "peak": 0.0, "cd": 0,
             "buf": np.zeros(bs * 4, dtype=np.float32)}

    def cb(indata, frames, ti, status):
        if status or state["detected"] or state["cd"] > 0:
            if state["cd"] > 0: state["cd"] -= 1
            return
        block = indata[:, 0]
        state["buf"] = np.roll(state["buf"], -len(block))
        state["buf"][-len(block):] = block
        peak = np.max(np.abs(block))
        if peak >= min_amp:
            buf = state["buf"]
            pi = np.argmax(np.abs(buf))
            h = bs // 2
            s = max(0, pi - h); e = min(len(buf), s + bs); s = max(0, e - bs)
            a = buf[s:e]
            if len(a) < bs: a = np.pad(a, (0, bs - len(a)))
            state["fp"] = compute_spectral_fingerprint(a, sr)
            state["peak"] = float(np.max(np.abs(a)))
            state["detected"] = True
            state["cd"] = 20

    print(f"  👏  Palma 1/{CALIBRATION_CLAPS} — bata quando quiser...")

    with sd.InputStream(callback=cb, channels=1, samplerate=sr, blocksize=bs, dtype="float32"):
        i = 0
        while i < CALIBRATION_CLAPS:
            if state["detected"]:
                fingerprints.append(state["fp"])
                beep(1200, 120)
                print(f"  ✅  Capturada! (amplitude: {state['peak']:.3f})")
                i += 1
                state["detected"] = False; state["fp"] = None; state["peak"] = 0.0
                time.sleep(0.6)
                if i < CALIBRATION_CLAPS:
                    print(f"\n  👏  Palma {i+1}/{CALIBRATION_CLAPS} — bata quando quiser...")
            else:
                time.sleep(0.02)

    if len(fingerprints) < 3:
        print("\n  ❌  Poucas palmas. Tente novamente.\n")
        return calibrate_claps()

    avg = np.mean(fingerprints, axis=0)
    n = np.linalg.norm(avg)
    if n > 0: avg = avg / n

    sims = [cosine_similarity(fp, avg) for fp in fingerprints]
    print(f"\n  📊  Consistencia: media {np.mean(sims):.0%}, minima {np.min(sims):.0%}")

    if np.min(sims) < 0.60:
        print("  ⚠️  Palmas inconsistentes. Recalibrando...\n")
        return calibrate_claps()

    profile = {"fingerprint": avg.tolist(), "num_samples": len(fingerprints),
               "avg_similarity": float(np.mean(sims)), "min_similarity": float(np.min(sims)),
               "calibrated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        with open(CLAP_PROFILE_FILE, "w") as f:
            json.dump(profile, f, indent=2)
        print(f"\n  💾  Perfil salvo em: {CLAP_PROFILE_FILE}")
    except Exception as e:
        print(f"\n  ⚠️  Erro ao salvar: {e}")

    print("  ✅  Calibracao concluida!\n")
    beep(600, 100); beep(800, 100); beep(1000, 200)
    return avg


def load_clap_profile():
    if not os.path.exists(CLAP_PROFILE_FILE): return None
    try:
        with open(CLAP_PROFILE_FILE, "r") as f:
            p = json.load(f)
        fp = np.array(p["fingerprint"], dtype=np.float64)
        print(f"  📂  Perfil carregado ({p.get('calibrated_at','?')}, {p.get('avg_similarity',0):.0%})")
        return fp
    except:
        return None


# ── ACOES ───────────────────────────────────────────────

def execute_jarvis(trigger_source):
    global last_triggered
    with lock:
        now = time.time()
        if now - last_triggered < COOLDOWN:
            print(f"  ⏳ Cooldown...")
            return
        last_triggered = now

    print(f"\n  {'='*44}\n  🔥  JARVIS ATIVADO  via {trigger_source}\n  {'='*44}\n")
    play_startup_sound()

    # 1. Musica (primeiro — demora pra carregar)
    try:
        webbrowser.open(MUSIC_URL)
        print("  ✅  Musica tocando 🎸")
    except Exception as e:
        print(f"  ⚠️  Musica falhou: {e}")

    time.sleep(1)

    # 2. App
    try:
        subprocess.Popen(CLAUDE_APP, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("  ✅  App aberto")
    except Exception as e:
        print(f"  ⚠️  App falhou: {e}")

    time.sleep(3)

    # 3. Terminal com comando (por ultimo, fica por cima)
    try:
        cmd = f'start cmd /k "cd /d {CLAUDE_CODE_DIR} && {CLAUDE_CODE_CMD}"'
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("  ✅  Terminal rodando")
    except Exception as e:
        print(f"  ⚠️  Terminal falhou: {e}")

    print(f"\n  🎯  Escutando novamente em {COOLDOWN}s...\n")


# ── CLAP DETECTOR ───────────────────────────────────────

def clap_detector():
    global clap_fingerprint
    if clap_fingerprint is None:
        print("  ❌  Sem perfil de palmas.")
        return

    sr = CLAP_SAMPLE_RATE; bs = CLAP_BLOCK_SIZE
    clap_times = []; buf = np.zeros(bs * 4, dtype=np.float32)
    in_t = False; t_cd = 0

    print(f"  👏  Detector de palmas ... ON (similaridade minima: {CLAP_SIMILARITY_THRESH:.0%})")

    def cb(indata, frames, ti, status):
        nonlocal clap_times, buf, in_t, t_cd
        if status: return
        block = indata[:, 0]
        buf = np.roll(buf, -len(block)); buf[-len(block):] = block
        if t_cd > 0: t_cd -= 1; return
        peak = np.max(np.abs(block))
        if peak < CLAP_AMPLITUDE_THRESH: in_t = False; return
        if not in_t:
            in_t = True
            pi = np.argmax(np.abs(buf)); h = bs//2
            s = max(0, pi-h); e = min(len(buf), s+bs); s = max(0, e-bs)
            fp = compute_spectral_fingerprint(buf[s:e], sr)
            sim = cosine_similarity(fp, clap_fingerprint)
            if sim >= CLAP_SIMILARITY_THRESH:
                now = time.time()
                if not clap_times or (now - clap_times[-1]) > CLAP_MIN_INTERVAL:
                    clap_times.append(now)
                    clap_times = [t for t in clap_times if now - t <= CLAP_WINDOW]
                    cnt = len(clap_times)
                    bar = "█" * cnt + "░" * (CLAP_COUNT - cnt)
                    print(f"  👏  Palma! [{bar}] {cnt}/{CLAP_COUNT}  (sim: {sim:.0%})")
                    if cnt >= CLAP_COUNT:
                        clap_times = []
                        threading.Thread(target=execute_jarvis, args=(f"{CLAP_COUNT} PALMAS 👏",), daemon=True).start()
                t_cd = 3
            else:
                if sim > 0.40:
                    print(f"  🔇  Descartado (sim: {sim:.0%})")
                t_cd = 2

    try:
        with sd.InputStream(callback=cb, channels=1, samplerate=sr, blocksize=bs, dtype="float32"):
            while True: time.sleep(0.1)
    except Exception as e:
        print(f"\n  ❌  Erro no detector: {e}")


# ── SPEECH DETECTOR ─────────────────────────────────────

def numpy_to_audio_data(audio_np, sample_rate):
    audio_int16 = (audio_np * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    buf.seek(0)
    with sr.AudioFile(buf) as source:
        r = sr.Recognizer()
        return r.record(source)


def speech_detector():
    recognizer = sr.Recognizer()
    print(f'  🎤  Detector de voz ... ON (frase: "{" ".join(WAKE_WORDS)}, {" ".join(WAKE_CONTEXT[:1])}")')

    print("  🔇  Calibrando ruido (2s)...")
    try:
        noise = sd.rec(int(2 * VOICE_SAMPLE_RATE), samplerate=VOICE_SAMPLE_RATE, channels=1, dtype="float32")
        sd.wait()
        vt = max(VOICE_SILENCE_THRESH, np.mean(np.abs(noise)) * 3)
        print(f"  ✅  Calibracao de voz OK\n")
    except:
        print("  ❌  Microfone indisponivel para voz.\n"); return

    while True:
        try:
            audio = sd.rec(int(VOICE_CHUNK_SEC * VOICE_SAMPLE_RATE), samplerate=VOICE_SAMPLE_RATE, channels=1, dtype="float32")
            sd.wait()
            flat = audio.flatten()
            if np.max(np.abs(flat)) < vt: continue
            ad = numpy_to_audio_data(flat, VOICE_SAMPLE_RATE)
            try:
                text = recognizer.recognize_google(ad, language=VOICE_LANGUAGE).lower()
                print(f'  🎤  Ouvi: "{text}"')
                hw = any(w in text for w in WAKE_WORDS)
                hc = any(c in text for c in WAKE_CONTEXT)
                if hw and hc:
                    threading.Thread(target=execute_jarvis, args=('VOZ 🎤',), daemon=True).start()
                    time.sleep(COOLDOWN)
                elif hw:
                    print(f'  💡  Falta contexto ({WAKE_CONTEXT})')
            except sr.UnknownValueError: pass
            except sr.RequestError: time.sleep(5)
        except: time.sleep(1)


# ── MAIN ────────────────────────────────────────────────

def main():
    global clap_fingerprint
    os.system("cls" if os.name == "nt" else "clear")
    print(f"""
    ╔══════════════════════════════════════════════════════╗
    ║          🤖  Max                                     ║
    ║          ─────────────────────────                    ║
    ╠══════════════════════════════════════════════════════╣
    ║  👏  {CLAP_COUNT} palmas   |   🎤  "{WAKE_WORDS[0]}, {WAKE_CONTEXT[0]}"     ║
    ║  Ctrl+C para desativar                               ║
    ╚══════════════════════════════════════════════════════╝
    """)

    fc = "--calibrar" in sys.argv or "--calibrate" in sys.argv
    if not fc: clap_fingerprint = load_clap_profile()
    if clap_fingerprint is None or fc:
        print("  📋  " + ("Recalibrando..." if fc else "Nenhum perfil. Vamos calibrar!") + "\n")
        clap_fingerprint = calibrate_claps()

    print("  Inicializando...\n")
    play_listening_sound()

    threading.Thread(target=clap_detector, daemon=True).start()
    time.sleep(0.5)
    threading.Thread(target=speech_detector, daemon=True).start()
    time.sleep(4)

    print(f"  {'='*44}\n  ✅  MAX AO SEU DISPOR — Esperando comando...\n  {'='*44}\n")

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n  {'='*44}\n  👋  MAX descansando...\n  {'='*44}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()

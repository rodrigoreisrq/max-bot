"""
╔══════════════════════════════════════════════════════════╗
║  JARVIS v2.0 mac — INFUSER AUTOMATION TRIGGER           ║
║                                                          ║
║  Detecta:                                                ║
║    👏  2 palmas (fingerprint espectral)                   ║
║    🎤  "Jarvis, bora trabalhar"                           ║
║                                                          ║
║  Dispara:                                                ║
║    → Abre Claude App                                     ║
║    → Roda Claude Code no terminal                        ║
║    → Toca AC/DC - Back in Black no YouTube Music         ║
║                                                          ║
║  Uso:                                                    ║
║    python3 jarvis.py              (normal)               ║
║    python3 jarvis.py --calibrar   (recalibrar palmas)    ║
║                                                          ║
║  v2.0: Detector de palmas por fingerprint espectral      ║
║        Grava SUAS palmas e compara em tempo real         ║
╚══════════════════════════════════════════════════════════╝
"""

import sys
import subprocess
import json

# ── CHECK DEPENDENCIES ──────────────────────────────────────
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
    print(f"\n⚠️  Pacotes faltando: {', '.join(missing)}")
    print(f"   Rode: pip3 install {' '.join(missing)}")
    print(f"   Depois execute este script novamente.\n")
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

# ╔════════════════════════════════════════════════════════════╗
# ║  CONFIGURAÇÃO — AJUSTE AQUI                               ║
# ╠════════════════════════════════════════════════════════════╣

# -- Palmas (Fingerprint) --
CLAP_COUNT            = 2       # Quantas palmas pra ativar
CLAP_WINDOW           = 2.5     # Janela de tempo (segundos) pra completar as palmas
CLAP_AMPLITUDE_THRESH = 0.25    # Amplitude mínima pra iniciar análise espectral
                                # (aumentado pra ignorar teclado do MacBook)
CLAP_SIMILARITY_THRESH = 0.70   # Similaridade mínima (0.60 = tolerante, 0.80 = rígido)
CLAP_MIN_INTERVAL     = 0.15    # Intervalo mínimo entre palmas (segundos)
CLAP_SAMPLE_RATE      = 44100
CLAP_BLOCK_SIZE       = 2048

# Arquivo de calibração
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLAP_PROFILE_FILE = os.path.join(SCRIPT_DIR, "jarvis_clap_profile.json")
CALIBRATION_CLAPS = 5

# -- Voz --
WAKE_WORDS        = ["jarvis"]
WAKE_CONTEXT      = ["trabalhar", "bora", "trabalho", "vamos"]
VOICE_LANGUAGE     = "pt-BR"
VOICE_SAMPLE_RATE  = 16000
VOICE_CHUNK_SEC    = 4
VOICE_SILENCE_THRESH = 0.02

# -- Ações (macOS) --
CLAUDE_APP        = "Claude"                    # Nome do app no /Applications
CLAUDE_CODE_CMD   = "claude --dangerously-skip-permissions"
MUSIC_URL         = "https://music.youtube.com/watch?v=pAgnJDJN4VA"

# -- Geral --
COOLDOWN          = 15

# ╚════════════════════════════════════════════════════════════╝


# ── STATE ───────────────────────────────────────────────────
last_triggered = 0
lock = threading.Lock()
clap_fingerprint = None


# ── SOUNDS (macOS — via afplay, sem conflito com InputStream) ──

def beep(sound="Tink"):
    """Toca um som do sistema macOS sem conflitar com sounddevice."""
    try:
        path = f"/System/Library/Sounds/{sound}.aiff"
        if os.path.exists(path):
            subprocess.Popen(
                ["afplay", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.15)
    except Exception:
        pass


def play_startup_sound():
    """Som de ativação do Jarvis."""
    for s in ["Tink", "Tink", "Pop", "Glass"]:
        beep(s)
        time.sleep(0.1)


def play_listening_sound():
    """Beep curto ao iniciar."""
    beep("Pop")


# ── SPECTRAL FINGERPRINT ENGINE ─────────────────────────────

def compute_spectral_fingerprint(audio_block: np.ndarray, sample_rate: int) -> np.ndarray:
    """
    Calcula o fingerprint espectral de um bloco de áudio.
    Palmas = broadband (energia espalhada). Voz = narrowband.
    """
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


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Similaridade do cosseno entre dois vetores (0 a 1)."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


# ── CALIBRAÇÃO ──────────────────────────────────────────────

def calibrate_claps() -> np.ndarray:
    """
    Grava o fingerprint espectral das palmas do usuário.
    Usa InputStream contínuo (sem gaps) pra não perder nenhuma palma.
    """
    print()
    print("  ╔════════════════════════════════════════════╗")
    print("  ║  👏  CALIBRAÇÃO DE PALMAS                  ║")
    print("  ╠════════════════════════════════════════════╣")
    print(f"  ║  Bata {CALIBRATION_CLAPS} palmas, uma de cada vez.          ║")
    print("  ║  Espere o ✅ antes de bater a próxima.     ║")
    print("  ║  Bata como você bateria normalmente.       ║")
    print("  ╚════════════════════════════════════════════╝")
    print()

    fingerprints = []
    sample_rate = CLAP_SAMPLE_RATE
    block_size = CLAP_BLOCK_SIZE
    min_amplitude = 0.05

    # Estado compartilhado com o callback
    state = {
        "detected": False,
        "fingerprint": None,
        "peak_amp": 0.0,
        "cooldown": 0,
        "buffer": np.zeros(block_size * 4, dtype=np.float32),
    }

    def cal_callback(indata, frames, time_info, status):
        if status:
            return
        if state["detected"] or state["cooldown"] > 0:
            if state["cooldown"] > 0:
                state["cooldown"] -= 1
            return

        block = indata[:, 0]

        # Atualizar buffer contínuo
        state["buffer"] = np.roll(state["buffer"], -len(block))
        state["buffer"][-len(block):] = block

        peak = np.max(np.abs(block))

        if peak >= min_amplitude:
            # Pegar o melhor bloco do buffer
            buf = state["buffer"]
            peak_idx = np.argmax(np.abs(buf))
            half = block_size // 2
            start = max(0, peak_idx - half)
            end = min(len(buf), start + block_size)
            start = max(0, end - block_size)

            analysis = buf[start:end]
            if len(analysis) < block_size:
                analysis = np.pad(analysis, (0, block_size - len(analysis)))

            fp = compute_spectral_fingerprint(analysis, sample_rate)
            state["fingerprint"] = fp
            state["peak_amp"] = float(np.max(np.abs(analysis)))
            state["detected"] = True
            state["cooldown"] = 20  # Ignorar eco

    print(f"  👏  Palma 1/{CALIBRATION_CLAPS} — bata quando quiser...")

    with sd.InputStream(
        callback=cal_callback,
        channels=1,
        samplerate=sample_rate,
        blocksize=block_size,
        dtype="float32",
    ):
        i = 0
        while i < CALIBRATION_CLAPS:
            if state["detected"]:
                fingerprints.append(state["fingerprint"])
                beep("Pop")
                print(f"  ✅  Capturada! (amplitude: {state['peak_amp']:.3f})")
                i += 1

                # Reset
                state["detected"] = False
                state["fingerprint"] = None
                state["peak_amp"] = 0.0

                time.sleep(0.6)

                if i < CALIBRATION_CLAPS:
                    print(f"\n  👏  Palma {i + 1}/{CALIBRATION_CLAPS} — bata quando quiser...")
            else:
                time.sleep(0.02)  # Polling leve

    if len(fingerprints) < 3:
        print("\n  ❌  Poucas palmas capturadas. Tente novamente.\n")
        return calibrate_claps()

    avg_fingerprint = np.mean(fingerprints, axis=0)
    norm = np.linalg.norm(avg_fingerprint)
    if norm > 0:
        avg_fingerprint = avg_fingerprint / norm

    similarities = [cosine_similarity(fp, avg_fingerprint) for fp in fingerprints]
    avg_sim = np.mean(similarities)
    min_sim = np.min(similarities)

    print()
    print(f"  📊  Consistência das palmas:")
    print(f"      Média:  {avg_sim:.2%}")
    print(f"      Mínima: {min_sim:.2%}")

    if min_sim < 0.60:
        print(f"  ⚠️  Palmas inconsistentes. Tente bater de forma mais uniforme.")
        print(f"      Recalibrando...\n")
        return calibrate_claps()

    profile = {
        "fingerprint": avg_fingerprint.tolist(),
        "num_samples": len(fingerprints),
        "avg_similarity": float(avg_sim),
        "min_similarity": float(min_sim),
        "calibrated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        with open(CLAP_PROFILE_FILE, "w") as f:
            json.dump(profile, f, indent=2)
        print(f"\n  💾  Perfil salvo em: {CLAP_PROFILE_FILE}")
    except Exception as e:
        print(f"\n  ⚠️  Erro ao salvar perfil: {e}")

    print("  ✅  Calibração concluída!\n")
    beep("Tink")
    beep("Pop")
    beep("Glass")

    return avg_fingerprint


def load_clap_profile() -> np.ndarray | None:
    """Carrega o perfil de palmas do arquivo."""
    if not os.path.exists(CLAP_PROFILE_FILE):
        return None
    try:
        with open(CLAP_PROFILE_FILE, "r") as f:
            profile = json.load(f)
        fp = np.array(profile["fingerprint"], dtype=np.float64)
        date = profile.get("calibrated_at", "desconhecido")
        sim = profile.get("avg_similarity", 0)
        print(f"  📂  Perfil de palmas carregado")
        print(f"      Calibrado em: {date}")
        print(f"      Consistência: {sim:.2%}")
        return fp
    except Exception as e:
        print(f"  ⚠️  Erro ao carregar perfil: {e}")
        return None


# ── ACTIONS (macOS) ─────────────────────────────────────────

def execute_jarvis(trigger_source: str):
    """Executa todas as ações quando ativado."""
    global last_triggered

    with lock:
        now = time.time()
        if now - last_triggered < COOLDOWN:
            remaining = int(COOLDOWN - (now - last_triggered))
            print(f"  ⏳ Cooldown ativo. Aguarde {remaining}s...")
            return
        last_triggered = now

    print()
    print("  ══════════════════════════════════════════")
    print(f"  🔥  JARVIS ATIVADO  via {trigger_source}")
    print("  ══════════════════════════════════════════")
    print()

    play_startup_sound()

    # 1. Tocar música (primeiro — demora pra carregar)
    try:
        webbrowser.open(MUSIC_URL)
        print("  ✅  AC/DC - Back in Black 🎸")
    except Exception as e:
        print(f"  ⚠️  Música falhou: {e}")

    time.sleep(1)

    # 2. Abrir Claude App
    try:
        subprocess.Popen(
            ["open", "-a", CLAUDE_APP],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("  ✅  Claude App aberto")
    except Exception as e:
        print(f"  ⚠️  Claude App falhou: {e}")
        print(f"      Verifique se 'Claude' está em /Applications")

    time.sleep(3)

    # 3. Abrir Terminal com Claude Code (por último, fica por cima)
    try:
        # Abre o Claude Code e depois de 3s manda Enter pra aceitar o trust
        apple_script = f'''
        tell application "Terminal"
            activate
            do script "{CLAUDE_CODE_CMD}"
        end tell
        delay 3
        tell application "Terminal"
            activate
        end tell
        tell application "System Events"
            tell process "Terminal"
                keystroke return
            end tell
        end tell
        '''
        subprocess.Popen(
            ["osascript", "-e", apple_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("  ✅  Claude Code rodando no Terminal")
    except Exception as e:
        print(f"  ⚠️  Claude Code falhou: {e}")

    print()
    print(f"  🎯  Escutando novamente em {COOLDOWN}s...")
    print()


# ── CLAP DETECTOR v2 (SPECTRAL FINGERPRINT) ────────────────

def clap_detector():
    """Detecta palmas via fingerprint espectral."""
    global clap_fingerprint

    if clap_fingerprint is None:
        print("  ❌  Sem perfil de palmas. Abortando detector.")
        return

    sample_rate = CLAP_SAMPLE_RATE
    block_size = CLAP_BLOCK_SIZE

    clap_times = []
    buffer_blocks = 4
    audio_buffer = np.zeros(block_size * buffer_blocks, dtype=np.float32)
    in_transient = False
    transient_cooldown = 0

    print("  👏  Detector de palmas ........... ON (fingerprint)")
    print(f"      Similaridade mínima: {CLAP_SIMILARITY_THRESH:.0%}")

    def audio_callback(indata, frames, time_info, status):
        nonlocal clap_times, audio_buffer, in_transient, transient_cooldown

        if status:
            return

        block = indata[:, 0]

        audio_buffer = np.roll(audio_buffer, -len(block))
        audio_buffer[-len(block):] = block

        if transient_cooldown > 0:
            transient_cooldown -= 1
            return

        peak = np.max(np.abs(block))

        if peak < CLAP_AMPLITUDE_THRESH:
            in_transient = False
            return

        if not in_transient:
            in_transient = True

            peak_idx = np.argmax(np.abs(audio_buffer))
            half = block_size // 2
            start = max(0, peak_idx - half)
            end = min(len(audio_buffer), start + block_size)
            start = max(0, end - block_size)
            analysis_block = audio_buffer[start:end]

            fp = compute_spectral_fingerprint(analysis_block, sample_rate)
            similarity = cosine_similarity(fp, clap_fingerprint)

            if similarity >= CLAP_SIMILARITY_THRESH:
                now = time.time()

                if not clap_times or (now - clap_times[-1]) > CLAP_MIN_INTERVAL:
                    clap_times.append(now)
                    clap_times = [t for t in clap_times if now - t <= CLAP_WINDOW]

                    count = len(clap_times)
                    bar = "█" * count + "░" * (CLAP_COUNT - count)
                    print(f"  👏  Palma! [{bar}] {count}/{CLAP_COUNT}  (sim: {similarity:.0%})")

                    if count >= CLAP_COUNT:
                        clap_times = []
                        threading.Thread(
                            target=execute_jarvis,
                            args=("2 PALMAS 👏",),
                            daemon=True,
                        ).start()

                transient_cooldown = 3
            else:
                if similarity > 0.40:
                    print(f"  🔇  Som descartado (sim: {similarity:.0%}, precisa: {CLAP_SIMILARITY_THRESH:.0%})")
                transient_cooldown = 2

    try:
        with sd.InputStream(
            callback=audio_callback,
            channels=1,
            samplerate=sample_rate,
            blocksize=block_size,
            dtype="float32",
        ):
            while True:
                time.sleep(0.1)
    except Exception as e:
        print(f"\n  ❌  Erro no detector de palmas: {e}")
        print("      Verifique se o microfone está permitido em:")
        print("      Ajustes do Sistema → Privacidade → Microfone → Terminal\n")


# ── SPEECH DETECTOR ─────────────────────────────────────────

def numpy_to_audio_data(audio_np: np.ndarray, sample_rate: int) -> sr.AudioData:
    """Converte array numpy para sr.AudioData."""
    audio_int16 = (audio_np * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    buf.seek(0)
    with sr.AudioFile(buf) as source:
        recognizer = sr.Recognizer()
        audio_data = recognizer.record(source)
    return audio_data


def speech_detector():
    """Detecta "Jarvis, bora trabalhar" via Google Speech Recognition."""
    recognizer = sr.Recognizer()

    print("  🎤  Detector de voz .............. ON")
    print(f'      Frase: "Jarvis, bora trabalhar"')

    print("  🔇  Calibrando ruído ambiente (2s)...")
    try:
        noise_sample = sd.rec(
            int(2 * VOICE_SAMPLE_RATE),
            samplerate=VOICE_SAMPLE_RATE,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        ambient_level = np.mean(np.abs(noise_sample))
        voice_threshold = max(VOICE_SILENCE_THRESH, ambient_level * 3)
        print(f"  ✅  Calibração concluída (limiar: {voice_threshold:.4f})\n")
    except Exception as e:
        print(f"\n  ❌  Erro ao acessar microfone: {e}")
        print("      O detector de voz será desativado.\n")
        return

    while True:
        try:
            audio_np = sd.rec(
                int(VOICE_CHUNK_SEC * VOICE_SAMPLE_RATE),
                samplerate=VOICE_SAMPLE_RATE,
                channels=1,
                dtype="float32",
            )
            sd.wait()

            audio_flat = audio_np.flatten()
            peak = np.max(np.abs(audio_flat))
            if peak < voice_threshold:
                continue

            audio_data = numpy_to_audio_data(audio_flat, VOICE_SAMPLE_RATE)

            try:
                text = recognizer.recognize_google(
                    audio_data, language=VOICE_LANGUAGE
                ).lower()

                print(f'  🎤  Ouvi: "{text}"')

                has_wake = any(w in text for w in WAKE_WORDS)
                has_context = any(c in text for c in WAKE_CONTEXT)

                if has_wake and has_context:
                    threading.Thread(
                        target=execute_jarvis,
                        args=('VOZ: "Jarvis, bora trabalhar" 🎤',),
                        daemon=True,
                    ).start()
                    time.sleep(COOLDOWN)
                elif has_wake:
                    print('  💡  Ouvi "Jarvis" mas falta "bora trabalhar"')

            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"  ⚠️  Erro no Google Speech: {e}")
                time.sleep(5)

        except Exception as e:
            print(f"  ⚠️  Erro na captura de voz: {e}")
            time.sleep(1)


# ── MAIN ────────────────────────────────────────────────────

def print_banner():
    os.system("clear")
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║                                                      ║
    ║          🤖  J A R V I S   v 2 . 0   mac             ║
    ║          ─────────────────────────────                ║
    ║          I N F U S E R                                ║
    ║                                                      ║
    ╠══════════════════════════════════════════════════════╣
    ║                                                      ║
    ║  Gatilhos:                                           ║
    ║    👏  2 palmas sequenciais (fingerprint espectral)   ║
    ║    🎤  "Jarvis, bora trabalhar"                       ║
    ║                                                      ║
    ║  Ações:                                              ║
    ║    → Abre Claude App                                 ║
    ║    → Roda Claude Code no Terminal                    ║
    ║    → Toca AC/DC - Back in Black 🎸                   ║
    ║                                                      ║
    ║  Comandos:                                           ║
    ║    python3 jarvis.py              (iniciar)          ║
    ║    python3 jarvis.py --calibrar   (recalibrar)       ║
    ║                                                      ║
    ║  Ctrl+C para desativar                               ║
    ║                                                      ║
    ╚══════════════════════════════════════════════════════╝
    """)


def main():
    global clap_fingerprint

    print_banner()

    force_calibrate = "--calibrar" in sys.argv or "--calibrate" in sys.argv

    if not force_calibrate:
        clap_fingerprint = load_clap_profile()

    if clap_fingerprint is None or force_calibrate:
        if not force_calibrate:
            print("  📋  Nenhum perfil de palmas encontrado.")
            print("      Vamos calibrar agora!\n")
        else:
            print("  📋  Recalibrando palmas...\n")

        clap_fingerprint = calibrate_claps()

    print("  Inicializando detectores...\n")
    play_listening_sound()

    t_clap = threading.Thread(target=clap_detector, daemon=True, name="ClapDetector")
    t_clap.start()

    time.sleep(0.5)

    t_voice = threading.Thread(target=speech_detector, daemon=True, name="VoiceDetector")
    t_voice.start()

    time.sleep(4)

    print("  ══════════════════════════════════════════")
    print("  ✅  JARVIS ONLINE — Esperando comando...")
    print("  ══════════════════════════════════════════\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n")
        print("  ══════════════════════════════════════════")
        print("  👋  Jarvis desativado. Até a próxima!")
        print("  ══════════════════════════════════════════\n")
        sys.exit(0)


if __name__ == "__main__":
    main()

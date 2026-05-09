# ═══════════════════════════════════════════════════════════════════════════
# 🤖 MAX BOT - Automação por Palmas e Voz (Windows) - COM INTERFACE GRÁFICA
# Versão: 2.0  |  Autor: Max Bot Project
# Descrição: Assistente de voz ativado por palmas ou comando "max"
#             com interface gráfica moderna em tkinter.
# ═══════════════════════════════════════════════════════════════════════════



# ───────────────────────────────────────────────────────────────────────────
# 📚 IMPORTAÇÃO DE BIBLIOTECAS PADRÃO DO PYTHON
# ───────────────────────────────────────────────────────────────────────────
import sys                         # Acesso a funções do sistema (ex: sys.exit)
import subprocess                  # Permite executar processos externos (abrir apps)
import json                        # Leitura e escrita de arquivos JSON (perfil de palmas)
import threading                   # Permite rodar múltiplas tarefas ao mesmo tempo
import time                        # Funções de tempo: sleep, time.time()
import webbrowser                  # Abre URLs no navegador padrão do sistema
import os                          # Operações do sistema operacional (paths, comandos)
import io                          # Manipulação de streams de bytes em memória
import wave                        # Criação/leitura de arquivos de áudio WAV
import queue                       # Fila thread-safe para comunicar entre threads
import tkinter as tk               # Biblioteca principal de interface gráfica
from tkinter import ttk            # Widgets temáticos do tkinter (Progressbar, etc.)
from tkinter import scrolledtext   # Widget de texto com barra de rolagem automática
from datetime import datetime      # Classe para trabalhar com datas e horas

# ───────────────────────────────────────────────────────────────────────────
# 📚 IMPORTAÇÃO DE BIBLIOTECAS EXTERNAS (pip install)
# ───────────────────────────────────────────────────────────────────────────
import numpy as np                 # Processamento numérico de arrays (áudio)
import sounddevice as sd           # Captura de áudio do microfone em tempo real
import speech_recognition as sr   # Reconhecimento de fala via Google Speech API
# pyttsx3 removido — voz agora usa PowerShell nativo do Windows

# ───────────────────────────────────────────────────────────────────────────
# 🔧 VERIFICAÇÃO DE DEPENDÊNCIAS ANTES DE INICIAR
# ───────────────────────────────────────────────────────────────────────────
REQUIRED = {                       # Dicionário: módulo_python -> nome_do_pacote_pip
    "speech_recognition": "SpeechRecognition",
    "sounddevice": "sounddevice",
    "numpy": "numpy",
}

missing = []                       # Lista que acumula os pacotes não instalados
for mod, pkg in REQUIRED.items():  # Itera cada par módulo/pacote
    try:
        __import__(mod)            # Tenta importar o módulo dinamicamente
    except ImportError:
        missing.append(pkg)        # Se falhar, adiciona à lista de faltando

if missing:                        # Se houver pacotes em falta, avisa e encerra
    print(f"\n⚠️  Pacotes em falta: {', '.join(missing)}")
    print(f"   Rode: pip install {' '.join(missing)}\n")
    sys.exit(1)                    # Código 1 = saída com erro

# ───────────────────────────────────────────────────────────────────────────
#  CONFIGURAÇÃO OPCIONAL DE VOLUME (PYCAW - só Windows)
# ───────────────────────────────────────────────────────────────────────────
VOLUME_AVAILABLE = False           # Flag: controle de volume disponível?
volume_control = None              # Referência ao objeto de controle de volume

try:
    from ctypes import cast, POINTER          # ctypes: interoperabilidade com C/DLL
    from comtypes import CLSCTX_ALL           # Contexto COM para ativar interfaces
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # API de áudio Windows

    devices = AudioUtilities.GetSpeakers()    # Obtém o dispositivo de saída de áudio padrão
    interface = devices.Activate(             # Ativa a interface de controle de volume
        IAudioEndpointVolume._iid_,           # GUID da interface IAudioEndpointVolume
        CLSCTX_ALL,                           # Contexto: todos os contextos COM
        None                                  # Sem parâmetros adicionais
    )
    volume_control = cast(interface, POINTER(IAudioEndpointVolume))  # Converte ponteiro COM
    VOLUME_AVAILABLE = True         # Marca como disponível se tudo funcionou
except Exception:
    pass                            # Silencia o erro; bot funciona sem controle de volume

# ───────────────────────────────────────────────────────────────────────────
# ⚙️ CONFIGURAÇÕES EDITÁVEIS — PERSONALIZE AQUI
# ───────────────────────────────────────────────────────────────────────────

# --- PALMAS ---
CLAP_COUNT = 2                     # Número de palmas necessárias para ativar
CLAP_WINDOW = 2.5                  # Janela de tempo (segundos) para contar as palmas
CLAP_AMPLITUDE_THRESH = 0.25       # Limiar mínimo de volume para considerar uma palma
CLAP_SIMILARITY_THRESH = 0.80      # Similaridade mínima (0-1) com o perfil calibrado
CLAP_MIN_INTERVAL = 0.15           # Intervalo mínimo (segundos) entre palmas distintas
CLAP_SAMPLE_RATE = 44100           # Taxa de amostragem do microfone (Hz) para palmas
CLAP_BLOCK_SIZE = 2048             # Tamanho do bloco de amostras processado por vez

# --- CALIBRAÇÃO ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))              # Diretório do script atual
CLAP_PROFILE_FILE = os.path.join(SCRIPT_DIR, "max_clap_profile.json")  # Caminho do perfil salvo
CALIBRATION_CLAPS = 5              # Quantidade de palmas coletadas na calibração

# --- VOZ ---
WAKE_WORDS = ["max"]               # Palavras que ativam o reconhecimento de comando
WAKE_CONTEXT = ["trabalhar", "bora", "trabalho", "vamos", "ajuda",
                 "hora", "chrome"]  # Palavras de contexto para ajudar o reconhecimento
VOICE_LANGUAGE = "pt-BR"           # Idioma do reconhecimento de fala (Google Speech)
VOICE_SAMPLE_RATE = 16000          # Taxa de amostragem do microfone para voz (Hz)
VOICE_CHUNK_SEC = 4                # Duração (segundos) de cada trecho de áudio capturado
VOICE_SILENCE_THRESH = 0.02        # Limiar mínimo de amplitude para processar o áudio

# --- APLICATIVOS (ajuste para o seu sistema) ---
CLAUDE_APP = r"C:\Users\User\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd"  # Caminho do VS Code
CLAUDE_CODE_DIR = r"C:\Users\Public"                         # Pasta de trabalho padrão
CLAUDE_CODE_CMD = "dir"                                      # Comando inicial no terminal
MUSIC_URL = "https://music.youtube.com/watch?v=-YQ8IbVIwPM" # URL da música de foco

# --- GERAL ---
COOLDOWN = 15                      # Segundos de espera após cada comando de voz

# ───────────────────────────────────────────────────────────────────────────
# 🗣️ SISTEMA DE VOZ TTS — PowerShell nativo do Windows
# ───────────────────────────────────────────────────────────────────────────
# Por que PowerShell em vez de pyttsx3?
#   pyttsx3 usa a API COM do Windows e conflita com tkinter: ambos disputam
#   o mesmo message loop do Windows, causando silêncio sem dar erro algum.
#   PowerShell usa System.Speech.Synthesis que roda em processo separado,
#   completamente isolado do Python — zero conflito, zero instalação extra.
# ───────────────────────────────────────────────────────────────────────────

tts_queue = queue.Queue()          # Fila thread-safe de textos a serem falados

def _tts_worker():
    """
    Thread dedicada que consome a fila tts_queue e fala cada texto via PowerShell.
    Cada fala vira um processo powershell.exe separado — sem conflito com tkinter.
    A thread fica bloqueada em tts_queue.get() quando não há nada para falar.
    """
    while True:
        texto = tts_queue.get()               # Aguarda próximo texto na fila (bloqueante)
        if texto is None:                      # Sentinela None = sinal para encerrar thread
            break
        try:
            # Escapa aspas simples duplicando-as (convenção do PowerShell)
            texto_safe = texto.replace("'", "''")

            # Script PowerShell que usa o motor de voz nativo do Windows (SAPI)
            # System.Speech está disponível em TODAS as versões do Windows 7+
            script = (
                "Add-Type -AssemblyName System.Speech; "          # Carrega assembly de fala
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "  # Cria sintetizador
                "$s.Rate = 1; "                                    # Velocidade: -10 (lento) a 10 (rápido)
                "$s.Volume = 100; "                                # Volume: 0 a 100
                f"$s.Speak('{texto_safe}')"                        # Fala o texto e aguarda terminar
            )

            # Executa PowerShell em processo separado, sem janela visível
            subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                timeout=30,                    # Timeout de 30s para evitar travar indefinidamente
                creationflags=subprocess.CREATE_NO_WINDOW  # Sem janela cmd aparecendo
            )
        except subprocess.TimeoutExpired:
            print("  ⚠️  TTS timeout — texto muito longo ou PowerShell travou")
        except Exception as e:
            print(f"  ⚠️  Erro no TTS: {e}")
        finally:
            tts_queue.task_done()              # Libera o slot na fila (permite join())

# Inicia thread TTS como daemon — encerra sozinha quando o programa fechar
_tts_thread = threading.Thread(target=_tts_worker, daemon=True, name="TTS-Worker")
_tts_thread.start()                            # Thread já aguardando na fila

# ───────────────────────────────────────────────────────────────────────────
# 🔒 VARIÁVEIS GLOBAIS COMPARTILHADAS ENTRE THREADS
# ───────────────────────────────────────────────────────────────────────────
last_triggered = 0                 # Timestamp da última ativação (controle de cooldown)
lock = threading.Lock()            # Trava para evitar condição de corrida entre threads
clap_fingerprint = None            # Vetor numpy com a "impressão digital" das palmas
log_queue = queue.Queue()          # Fila de mensagens para a interface gráfica
status_queue = queue.Queue()       # Fila de atualizações de status para a interface
# Nota: tts_queue já foi criada acima junto com o worker TTS

# ───────────────────────────────────────────────────────────────────────────
# 🔊 FUNÇÕES DE FEEDBACK SONORO (BEEPS DO SISTEMA)
# ───────────────────────────────────────────────────────────────────────────
def beep(freq=800, dur=100):
    """Emite um bipe sonoro usando o alto-falante interno do Windows."""
    try:
        import winsound              # Módulo exclusivo do Windows para sons do sistema
        winsound.Beep(freq, dur)     # freq = frequência em Hz, dur = duração em ms
    except Exception:
        pass                         # Ignora silenciosamente em outros sistemas

def play_startup_sound():
    """Sequência de bipes tocada ao iniciar o bot (som de 'ligar')."""
    beep(600, 150)   # Nota grave - início da sequência
    beep(800, 150)   # Nota média-baixa
    beep(1000, 150)  # Nota média
    beep(1200, 250)  # Nota aguda - fim da sequência (mais longa)

def play_listening_sound():
    """Dois bipes rápidos indicando que o bot está pronto para ouvir."""
    beep(800, 100)   # Primeiro bipe de atenção
    beep(1000, 100)  # Segundo bipe confirmando escuta ativa

# ───────────────────────────────────────────────────────────────────────────
# 📝 FUNÇÕES DE LOG PARA A INTERFACE
# ───────────────────────────────────────────────────────────────────────────
def log(mensagem, tipo="info"):
    """
    Envia mensagem para a fila de log da interface gráfica.
    tipo: 'info', 'sucesso', 'erro', 'aviso', 'voz', 'palma', 'comando'
    """
    timestamp = datetime.now().strftime("%H:%M:%S")  # Formata hora atual HH:MM:SS
    log_queue.put((timestamp, mensagem, tipo))        # Coloca tupla na fila thread-safe

def set_status(status, ativo=True):
    """Envia atualização de status para a barra de status da interface."""
    status_queue.put((status, ativo))  # Coloca o novo status na fila

# ───────────────────────────────────────────────────────────────────────────
# 🗣️ FUNÇÃO PÚBLICA DE VOZ — enfileira texto para a thread TTS dedicada
# ───────────────────────────────────────────────────────────────────────────
def falar(texto):
    """
    Enfileira um texto para ser falado pela thread TTS dedicada.
    Não bloqueia: retorna imediatamente enquanto o áudio toca em background.
    O log é registrado aqui para aparecer na interface no momento da chamada.
    """
    log(f"MAX: {texto}", "voz")    # Registra no log visual imediatamente
    tts_queue.put(texto)           # Coloca o texto na fila; a thread TTS irá processá-lo

# ───────────────────────────────────────────────────────────────────────────
# 🧠 MOTOR DE FINGERPRINT ESPECTRAL (ANÁLISE DE FREQUÊNCIAS)
# ───────────────────────────────────────────────────────────────────────────
def compute_spectral_fingerprint(audio_block, sample_rate):
    """
    Calcula a 'impressão digital espectral' de um bloco de áudio.
    Divide o espectro em 20 bandas logarítmicas e mede a energia de cada uma.
    Retorna vetor normalizado que representa o 'perfil sonoro' do sinal.
    """
    windowed = audio_block * np.hanning(len(audio_block))  # Aplica janela de Hanning para reduzir vazamento espectral
    fft = np.fft.rfft(windowed)                             # FFT real: converte tempo → frequência
    magnitude = np.abs(fft)                                  # Magnitude de cada componente de frequência
    freqs = np.fft.rfftfreq(len(audio_block), 1.0 / sample_rate)  # Frequências correspondentes a cada bin da FFT

    band_edges = np.logspace(                                # Cria 21 bordas de bandas em escala logarítmica
        np.log10(100),                                       # Começa em 100 Hz (voz/palmas)
        np.log10(min(20000, sample_rate // 2)),              # Termina em 20kHz ou Nyquist
        21                                                   # 21 bordas = 20 bandas
    )

    band_energies = []                                       # Lista de energia por banda
    for i in range(len(band_edges) - 1):                     # Para cada uma das 20 bandas
        mask = (freqs >= band_edges[i]) & (freqs < band_edges[i + 1])  # Máscara de bins na banda
        if np.any(mask):                                     # Se há frequências nesta banda
            band_energies.append(np.mean(magnitude[mask] ** 2))  # Energia média (potência)
        else:
            band_energies.append(0.0)                        # Banda vazia = energia zero

    fingerprint = np.array(band_energies, dtype=np.float64) # Converte lista em array numpy
    norm = np.linalg.norm(fingerprint)                       # Calcula norma L2 do vetor
    if norm > 0:
        fingerprint = fingerprint / norm                     # Normaliza para vetor unitário

    return fingerprint                                       # Retorna vetor de 20 dimensões

def cosine_similarity(a, b):
    """
    Calcula similaridade cosseno entre dois vetores (0 = oposto, 1 = idêntico).
    Usada para comparar o fingerprint de um som com o perfil de palma calibrado.
    """
    dot = np.dot(a, b)                      # Produto escalar entre os vetores
    na, nb = np.linalg.norm(a), np.linalg.norm(b)  # Normas dos vetores
    if na == 0 or nb == 0:                  # Evita divisão por zero
        return 0.0
    return float(dot / (na * nb))           # Similaridade cosseno: cos(θ)

# ───────────────────────────────────────────────────────────────────────────
# 🎯 CALIBRAÇÃO DE PALMAS
# ───────────────────────────────────────────────────────────────────────────
def calibrate_claps(callback_log=None):
    """
    Coleta amostras de palmas do usuário e salva um perfil JSON.
    callback_log: função opcional para enviar mensagens de progresso à interface.
    Retorna vetor numpy com o fingerprint médio das palmas calibradas.
    """
    def _log(msg):
        """Helper interno que usa callback ou print."""
        if callback_log:
            callback_log(msg)   # Envia para a interface gráfica
        else:
            print(msg)          # Fallback para o terminal

    _log("👏 Iniciando calibração — bata as palmas quando solicitado")

    fingerprints = []           # Lista que acumulará os fingerprints das palmas
    sr_rate = CLAP_SAMPLE_RATE  # Taxa de amostragem do microfone
    bs = CLAP_BLOCK_SIZE        # Tamanho do bloco de áudio
    min_amp = 0.05              # Amplitude mínima para iniciar detecção na calibração

    # Estado compartilhado entre o callback do sounddevice e o loop principal
    state = {
        "detected": False,      # Sinaliza que uma palma foi detectada
        "fp": None,             # Fingerprint da palma detectada
        "peak": 0.0,            # Amplitude de pico da palma
        "cd": 0,                # Cooldown em blocos (evita detectar eco)
        "buf": np.zeros(bs * 4, dtype=np.float32)  # Buffer circular de áudio
    }

    def cb(indata, frames, ti, status):
        """Callback chamado pelo sounddevice a cada bloco de áudio capturado."""
        if status or state["detected"] or state["cd"] > 0:
            if state["cd"] > 0:
                state["cd"] -= 1   # Decrementa cooldown a cada bloco
            return                  # Ignora bloco se já detectou ou em cooldown

        block = indata[:, 0]        # Extrai canal mono (coluna 0 do array de entrada)
        state["buf"] = np.roll(state["buf"], -len(block))  # Desloca buffer circular
        state["buf"][-len(block):] = block                  # Insere novo bloco no fim

        peak = np.max(np.abs(block))  # Amplitude máxima do bloco atual

        if peak >= min_amp:           # Se o som passou do limiar mínimo
            buf = state["buf"]        # Referência ao buffer circular atual
            pi = np.argmax(np.abs(buf))  # Índice da amostra de maior amplitude
            h = bs // 2                  # Metade do bloco de análise
            s = max(0, pi - h)           # Início da janela centrada no pico
            e = min(len(buf), s + bs)    # Fim da janela
            s = max(0, e - bs)           # Ajuste para garantir tamanho fixo

            a = buf[s:e]                 # Extrai trecho centrado no pico
            if len(a) < bs:
                a = np.pad(a, (0, bs - len(a)))  # Completa com zeros se necessário

            state["fp"] = compute_spectral_fingerprint(a, sr_rate)  # Calcula fingerprint
            state["peak"] = float(np.max(np.abs(a)))                 # Salva amplitude de pico
            state["detected"] = True     # Sinaliza detecção para o loop principal
            state["cd"] = 20             # Define cooldown de 20 blocos (~1 segundo)

    _log(f"👏 Palma 1/{CALIBRATION_CLAPS} — bata quando quiser...")

    # Abre o stream de áudio e aguarda as palmas do usuário
    with sd.InputStream(callback=cb, channels=1, samplerate=sr_rate,
                        blocksize=bs, dtype="float32"):
        i = 0                           # Contador de palmas capturadas
        while i < CALIBRATION_CLAPS:   # Repete até ter todas as palmas
            if state["detected"]:       # Se o callback detectou uma palma
                fingerprints.append(state["fp"])  # Armazena fingerprint
                beep(1200, 120)          # Bipe de confirmação
                _log(f"✅ Capturada! (amplitude: {state['peak']:.3f})")
                i += 1                   # Incrementa contador
                state["detected"] = False  # Reseta flag de detecção
                state["fp"] = None         # Limpa fingerprint temporário
                state["peak"] = 0.0        # Limpa pico temporário
                time.sleep(0.6)            # Pausa para evitar dupla detecção
                if i < CALIBRATION_CLAPS:
                    _log(f"\n👏 Palma {i+1}/{CALIBRATION_CLAPS} — bata quando quiser...")
            else:
                time.sleep(0.02)       # Aguarda 20ms antes de checar novamente

    if len(fingerprints) < 3:          # Exige pelo menos 3 palmas válidas
        _log("❌ Poucas palmas. Tente novamente.")
        return calibrate_claps(callback_log)  # Reinicia calibração recursivamente

    avg = np.mean(fingerprints, axis=0)  # Média dos fingerprints coletados
    n = np.linalg.norm(avg)              # Norma do vetor médio
    if n > 0:
        avg = avg / n                    # Normaliza o vetor médio

    sims = [cosine_similarity(fp, avg) for fp in fingerprints]  # Similaridade de cada amostra com a média
    _log(f"📊 Consistência: média {np.mean(sims):.0%}, mínima {np.min(sims):.0%}")

    if np.min(sims) < 0.60:             # Se palmas muito inconsistentes
        _log("⚠️ Palmas inconsistentes. Recalibrando...")
        return calibrate_claps(callback_log)  # Tenta novamente

    # Monta dicionário com dados do perfil para salvar em JSON
    profile = {
        "fingerprint": avg.tolist(),            # Vetor convertido para lista (serializável)
        "num_samples": len(fingerprints),       # Quantidade de amostras usadas
        "avg_similarity": float(np.mean(sims)), # Consistência média das palmas
        "min_similarity": float(np.min(sims)),  # Pior consistência observada
        "calibrated_at": time.strftime("%Y-%m-%d %H:%M:%S")  # Data/hora da calibração
    }

    try:
        with open(CLAP_PROFILE_FILE, "w") as f:  # Abre arquivo JSON para escrita
            json.dump(profile, f, indent=2)       # Serializa dicionário em JSON formatado
        _log(f"💾 Perfil salvo em: {CLAP_PROFILE_FILE}")
    except Exception as e:
        _log(f"⚠️ Erro ao salvar: {e}")

    _log("✅ Calibração concluída!")
    beep(600, 100); beep(800, 100); beep(1000, 200)  # Fanfarra de conclusão
    return avg                                         # Retorna fingerprint médio

def load_clap_profile():
    """
    Tenta carregar o perfil de palmas salvo em JSON.
    Retorna vetor numpy ou None se não existir/inválido.
    """
    if not os.path.exists(CLAP_PROFILE_FILE):  # Verifica se o arquivo existe
        return None
    try:
        with open(CLAP_PROFILE_FILE, "r") as f:         # Abre arquivo para leitura
            p = json.load(f)                              # Parseia o JSON
        fp = np.array(p["fingerprint"], dtype=np.float64)  # Reconverte lista → array numpy
        log(f"Perfil carregado ({p.get('calibrated_at','?')}, consistência {p.get('avg_similarity',0):.0%})", "sucesso")
        return fp                                         # Retorna fingerprint carregado
    except Exception:
        return None                                       # Retorna None em caso de erro

# ───────────────────────────────────────────────────────────────────────────
# ⚡ SISTEMA DE COMANDOS DO MAX — AÇÕES EXECUTADAS
# ───────────────────────────────────────────────────────────────────────────
def executar_comando(comando_nome, detalhes=None):
    """
    Executa o comando indicado pelo nome.
    Cada bloco elif corresponde a uma ação diferente do bot.
    Todos os comandos respondem por voz usando falar().
    """
    log(f"Executando: {comando_nome}", "comando")  # Registra execução no log visual

    if comando_nome == "modo_trabalho":
        # --- MODO TRABALHO: abre música, VS Code e terminal ---
        falar("Ativando modo trabalho. Hora de focar, vamos lá!")  # Resposta de voz

        try:
            webbrowser.open(MUSIC_URL)                    # Abre URL da música no navegador padrão
            log("Música tocando 🎸", "sucesso")            # Confirma no log visual
            falar("Música de foco ativada")               # Confirma por voz
        except Exception as e:
            log(f"Música falhou: {e}", "erro")            # Registra falha no log
            falar("Não consegui abrir a música")          # Informa falha por voz

        time.sleep(1)  # Aguarda 1 segundo antes de abrir o próximo app

        try:
            if os.path.exists(CLAUDE_APP):                # Verifica se o VS Code existe no caminho
                subprocess.Popen(CLAUDE_APP, shell=True,  # Abre o VS Code como processo independente
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                log("VS Code aberto", "sucesso")          # Confirma abertura no log
                falar("Editor de código aberto e pronto") # Confirma por voz
            else:
                falar("Não encontrei o VS Code. Verifique o caminho nas configurações")
                log(f"Caminho não encontrado: {CLAUDE_APP}", "aviso")
        except Exception as e:
            log(f"VS Code falhou: {e}", "erro")
            falar("Tive um problema ao abrir o editor de código")

        time.sleep(2)  # Aguarda 2 segundos para o VS Code carregar

        try:
            cmd = f'start cmd /k "cd /d {CLAUDE_CODE_DIR} && {CLAUDE_CODE_CMD}"'  # Comando para abrir terminal na pasta certa
            subprocess.Popen(cmd, shell=True,             # Executa o comando do terminal
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            log("Terminal pronto", "sucesso")             # Confirma no log
            falar("Terminal de comando pronto. Boa codificação!")  # Voz de confirmação
        except Exception as e:
            log(f"Terminal falhou: {e}", "erro")
            falar("Não consegui abrir o terminal")

    elif comando_nome == "abrir_chrome":
        # --- ABRIR CHROME ---
        falar("Abrindo o Google Chrome agora")            # Voz antes de executar
        try:
            os.system('start chrome')                     # Comando Windows para abrir Chrome
            log("Chrome aberto", "sucesso")
            falar("Chrome aberto com sucesso")            # Confirma por voz
        except Exception as e:
            log(f"Chrome falhou: {e}", "erro")
            falar("Não consegui abrir o Chrome. Verifique se está instalado")

    elif comando_nome == "falar_hora":
        # --- FALAR A HORA ATUAL ---
        agora = datetime.now().strftime("%H e %M")        # Formata hora: "14 e 30"
        mensagem = f"São {agora} horas"                   # Monta frase completa
        falar(mensagem)                                   # Fala a hora
        log(f"🕐 {mensagem}", "info")                     # Registra no log

    elif comando_nome == "falar_data":
        # --- FALAR A DATA ATUAL ---
        hoje = datetime.now().strftime("%d de %B de %Y")  # Formata: "01 de January de 2025"
        meses = {                                          # Dicionário de tradução inglês → português
            "January": "janeiro",   "February": "fevereiro", "March": "março",
            "April": "abril",       "May": "maio",            "June": "junho",
            "July": "julho",        "August": "agosto",       "September": "setembro",
            "October": "outubro",   "November": "novembro",   "December": "dezembro"
        }
        for eng, por in meses.items():                    # Substitui nome do mês em inglês
            hoje = hoje.replace(eng, por)
        mensagem = f"Hoje é dia {hoje}"                   # Monta frase com data em português
        falar(mensagem)                                   # Fala a data
        log(f"📅 {mensagem}", "info")

    elif comando_nome == "abrir_notepad":
        # --- ABRIR BLOCO DE NOTAS ---
        falar("Abrindo bloco de notas para você")         # Voz antes de executar
        try:
            os.system('notepad.exe')                      # Executa o Notepad do Windows
            log("Bloco de notas aberto", "sucesso")
            falar("Bloco de notas pronto")                # Confirma por voz
        except Exception as e:
            log(f"Notepad falhou: {e}", "erro")
            falar("Não consegui abrir o bloco de notas")

    elif comando_nome == "aumentar_volume":
        # --- AUMENTAR VOLUME DO SISTEMA ---
        if VOLUME_AVAILABLE and volume_control:           # Só executa se pycaw disponível
            try:
                volume = volume_control.GetMasterVolumeLevelScalar()  # Lê volume atual (0.0–1.0)
                novo_volume = min(1.0, volume + 0.1)                  # Aumenta 10% com limite em 100%
                volume_control.SetMasterVolumeLevelScalar(novo_volume, None)  # Aplica novo volume
                msg = f"Volume aumentado para {int(novo_volume * 100)} por cento"
                falar(msg)                                # Confirma novo volume por voz
                log(f"🔊 {msg}", "sucesso")
            except Exception:
                falar("Não consegui ajustar o volume")
        else:
            falar("Controle de volume não disponível. Instale o pycaw para usar essa função")
            log("pycaw não instalado", "aviso")

    elif comando_nome == "diminuir_volume":
        # --- DIMINUIR VOLUME DO SISTEMA ---
        if VOLUME_AVAILABLE and volume_control:           # Só executa se pycaw disponível
            try:
                volume = volume_control.GetMasterVolumeLevelScalar()  # Lê volume atual
                novo_volume = max(0.0, volume - 0.1)                  # Diminui 10% com limite em 0%
                volume_control.SetMasterVolumeLevelScalar(novo_volume, None)  # Aplica novo volume
                msg = f"Volume diminuído para {int(novo_volume * 100)} por cento"
                falar(msg)                                # Confirma novo volume por voz
                log(f"🔉 {msg}", "sucesso")
            except Exception:
                falar("Não consegui ajustar o volume")
        else:
            falar("Controle de volume não disponível")
            log("pycaw não instalado", "aviso")

    elif comando_nome == "parar_musica":
        # --- PARAR MÚSICA (fecha o Chrome) ---
        falar("Parando a música agora")                   # Voz antes de executar
        try:
            os.system('taskkill /f /im chrome.exe')       # Força encerramento do Chrome
            log("Música parada", "sucesso")
            falar("Música encerrada. Foco total!")         # Confirma por voz
        except Exception:
            falar("Não consegui parar a música")
            log("Erro ao parar música", "erro")

    elif comando_nome == "ajuda":
        # --- LISTAR COMANDOS DISPONÍVEIS ---
        ajuda = (
            "Olá! Eu sou o MAX. Veja o que posso fazer: "
            "Diga bora trabalhar para ativar modo trabalho. "
            "Diga abre Chrome para abrir o navegador. "
            "Diga que horas são para saber a hora. "
            "Diga qual a data para saber o dia de hoje. "
            "Diga abre bloco de notas para abrir o Notepad. "
            "Diga aumenta volume ou diminui volume para controlar o áudio. "
            "Diga para a música para encerrar. "
            "Ou bata duas palmas para ativar o modo trabalho diretamente!"
        )
        falar(ajuda)                                      # Fala todos os comandos disponíveis
        log("Lista de ajuda exibida", "info")

    elif comando_nome == "encerrar":
        # --- ENCERRAR O BOT ---
        falar("Encerrando sistema. Até logo, senhor. Foi um prazer trabalhar com você!")
        log("Bot encerrando...", "aviso")
        time.sleep(3)                                     # Aguarda a fala terminar
        sys.exit(0)                                       # Encerra o processo Python

    else:
        log(f"Comando desconhecido: {comando_nome}", "erro")
        falar("Não reconheço esse comando. Diga ajuda para ver o que sei fazer")

# ───────────────────────────────────────────────────────────────────────────
# 👏 DETECTOR DE PALMAS — roda em thread separada
# ───────────────────────────────────────────────────────────────────────────
def clap_detector():
    """
    Thread que monitora o microfone em tempo real procurando por palmas.
    Compara cada som detectado com o fingerprint calibrado usando similaridade cosseno.
    Quando o número necessário de palmas é detectado, aciona o modo trabalho.
    """
    global clap_fingerprint
    if clap_fingerprint is None:             # Sem perfil não é possível detectar palmas
        log("Sem perfil de palmas. Use 'Calibrar'.", "erro")
        return

    sr_rate = CLAP_SAMPLE_RATE               # Taxa de amostragem configurada
    bs = CLAP_BLOCK_SIZE                     # Tamanho do bloco de áudio
    clap_times = []                          # Lista com timestamps das palmas recentes
    buf = np.zeros(bs * 4, dtype=np.float32) # Buffer circular de 4 blocos de áudio
    in_t = False                             # Flag: está dentro de um transiente sonoro?
    t_cd = 0                                 # Cooldown em blocos após detecção

    set_status("palmas", True)               # Atualiza status na interface gráfica
    log(f"Detector de palmas ativo (limiar: {CLAP_SIMILARITY_THRESH:.0%})", "sucesso")

    def cb(indata, frames, ti, status):
        """Callback chamado a cada bloco de áudio capturado pelo microfone."""
        nonlocal clap_times, buf, in_t, t_cd  # Acessa variáveis do escopo externo

        if status:                             # Se há erro no stream de áudio
            return                             # Ignora o bloco

        block = indata[:, 0]                   # Canal mono (coluna 0)
        buf = np.roll(buf, -len(block))        # Desloca buffer circular para a esquerda
        buf[-len(block):] = block              # Insere novo bloco no final do buffer

        if t_cd > 0:                           # Se ainda em cooldown
            t_cd -= 1                          # Decrementa cooldown
            return                             # Ignora este bloco

        peak = np.max(np.abs(block))           # Amplitude máxima do bloco
        if peak < CLAP_AMPLITUDE_THRESH:       # Som muito fraco = não é palma
            in_t = False                       # Reseta flag de transiente
            return

        if not in_t:                           # Primeiro bloco acima do limiar = início de transiente
            in_t = True

            pi = np.argmax(np.abs(buf))        # Posição do pico no buffer circular
            h = bs // 2                        # Metade do bloco de análise
            s = max(0, pi - h)                 # Início da janela centrada no pico
            e = min(len(buf), s + bs)          # Fim da janela
            s = max(0, e - bs)                 # Ajuste para garantir tamanho exato

            fp = compute_spectral_fingerprint(buf[s:e], sr_rate)  # Fingerprint do som detectado
            sim = cosine_similarity(fp, clap_fingerprint)          # Compara com perfil calibrado

            if sim >= CLAP_SIMILARITY_THRESH:  # Som suficientemente similar a uma palma
                now = time.time()              # Timestamp atual em segundos
                if not clap_times or (now - clap_times[-1]) > CLAP_MIN_INTERVAL:
                    clap_times.append(now)     # Registra timestamp desta palma
                    # Remove palmas fora da janela de tempo configurada
                    clap_times = [t for t in clap_times if now - t <= CLAP_WINDOW]
                    cnt = len(clap_times)       # Conta palmas válidas na janela

                    log(f"👏 Palma! {cnt}/{CLAP_COUNT} (sim: {sim:.0%})", "palma")

                    if cnt >= CLAP_COUNT:       # Atingiu número necessário de palmas
                        clap_times = []         # Reseta contagem de palmas
                        threading.Thread(       # Executa comando em thread separada
                            target=executar_comando,
                            args=("modo_trabalho",),
                            daemon=True
                        ).start()

                    t_cd = 3                    # Cooldown de 3 blocos após palma válida

            else:                               # Som não é similar a uma palma
                if sim > 0.40:                  # Mas parecido o suficiente para logar
                    log(f"🔇 Descartado (sim: {sim:.0%})", "info")
                t_cd = 2                        # Cooldown menor para sons descartados

    try:
        # Abre stream de entrada de áudio contínuo
        with sd.InputStream(callback=cb, channels=1, samplerate=sr_rate,
                            blocksize=bs, dtype="float32"):
            while True:
                time.sleep(0.1)                 # Mantém thread viva aguardando callbacks
    except Exception as e:
        log(f"Erro no detector de palmas: {e}", "erro")
        set_status("palmas", False)             # Atualiza status na interface

# ───────────────────────────────────────────────────────────────────────────
# 🎤 DETECTOR DE VOZ — roda em thread separada
# ───────────────────────────────────────────────────────────────────────────
def numpy_to_audio_data(audio_np, sample_rate):
    """
    Converte array numpy de áudio para objeto AudioData do speech_recognition.
    Etapas: float32 → int16 → bytes WAV → BytesIO → AudioFile → AudioData
    """
    audio_int16 = (audio_np * 32767).astype(np.int16)  # Converte float [-1,1] para int16 [-32767,32767]
    buf = io.BytesIO()                                   # Buffer em memória (sem arquivo em disco)
    with wave.open(buf, "wb") as wf:                     # Abre stream WAV para escrita
        wf.setnchannels(1)                               # Mono: 1 canal
        wf.setsampwidth(2)                               # 2 bytes por amostra (int16)
        wf.setframerate(sample_rate)                     # Taxa de amostragem em Hz
        wf.writeframes(audio_int16.tobytes())            # Escreve amostras como bytes
    buf.seek(0)                                          # Rebobina buffer para o início
    with sr.AudioFile(buf) as source:                    # Abre buffer como arquivo de áudio
        r = sr.Recognizer()                              # Cria reconhecedor temporário
        return r.record(source)                          # Retorna objeto AudioData

def speech_detector():
    """
    Thread que escuta continuamente o microfone e reconhece comandos de voz.
    Usa a palavra de ativação 'max' antes de interpretar o comando.
    Envia áudio ao Google Speech API para transcrição.
    """
    recognizer = sr.Recognizer()                          # Objeto principal de reconhecimento

    set_status("voz", True)                               # Atualiza status na interface
    log('Detector de voz ativo. Diga "max, [comando]"', "sucesso")
    log("Calibrando ruído de fundo (2s)...", "info")

    try:
        # Grava 2 segundos de silêncio para calibrar o limiar de silêncio
        noise = sd.rec(int(2 * VOICE_SAMPLE_RATE), samplerate=VOICE_SAMPLE_RATE,
                       channels=1, dtype="float32")
        sd.wait()                                         # Aguarda gravação terminar
        vt = max(VOICE_SILENCE_THRESH, np.mean(np.abs(noise)) * 3)  # Limiar = 3x o ruído médio
        log(f"Calibração de voz OK (limiar: {vt:.4f})", "sucesso")
    except Exception:
        log("Microfone indisponível para voz.", "erro")
        set_status("voz", False)
        return

    while True:                                           # Loop infinito de escuta
        try:
            # Grava VOICE_CHUNK_SEC segundos de áudio para análise
            audio = sd.rec(int(VOICE_CHUNK_SEC * VOICE_SAMPLE_RATE),
                           samplerate=VOICE_SAMPLE_RATE, channels=1, dtype="float32")
            sd.wait()                                     # Aguarda o trecho terminar
            flat = audio.flatten()                        # Converte array 2D em 1D

            if np.max(np.abs(flat)) < vt:                # Se o trecho é mais silencioso que o limiar
                continue                                  # Descarta e grava próximo trecho

            ad = numpy_to_audio_data(flat, VOICE_SAMPLE_RATE)  # Converte para AudioData

            try:
                # Envia áudio para a API do Google Speech (requer internet)
                texto = recognizer.recognize_google(ad, language=VOICE_LANGUAGE).lower()
                log(f'🎤 Ouvi: "{texto}"', "voz")        # Exibe transcrição no log

                tem_max = any(w in texto for w in WAKE_WORDS)  # Verifica se a palavra "max" está presente

                if tem_max:                               # Comando dirigido ao Max
                    comando_detectado = None              # Será preenchido abaixo

                    # Mapeamento de palavras-chave → comandos
                    if any(x in texto for x in ["bora", "trabalhar", "trabalho", "vamos"]):
                        comando_detectado = "modo_trabalho"
                    elif any(x in texto for x in ["chrome", "navegador", "google"]):
                        comando_detectado = "abrir_chrome"
                    elif any(x in texto for x in ["hora", "horas", "que horas"]):
                        comando_detectado = "falar_hora"
                    elif any(x in texto for x in ["data", "dia", "qual a data"]):
                        comando_detectado = "falar_data"
                    elif any(x in texto for x in ["bloco", "notas", "notepad"]):
                        comando_detectado = "abrir_notepad"
                    elif any(x in texto for x in ["aumenta", "aumentar", "mais alto"]):
                        comando_detectado = "aumentar_volume"
                    elif any(x in texto for x in ["diminui", "diminuir", "mais baixo"]):
                        comando_detectado = "diminuir_volume"
                    elif any(x in texto for x in ["para", "parar", "pare"]):
                        comando_detectado = "parar_musica"
                    elif any(x in texto for x in ["ajuda", "help", "comandos"]):
                        comando_detectado = "ajuda"
                    elif any(x in texto for x in ["encerrar", "desligar", "sair"]):
                        comando_detectado = "encerrar"    # Comando de emergência

                    if comando_detectado:                 # Se algum comando foi mapeado
                        log(f"✅ Comando: {comando_detectado}", "sucesso")
                        falar("Entendido!")               # Voz de confirmação de reconhecimento
                        threading.Thread(                 # Executa em thread separada
                            target=executar_comando,
                            args=(comando_detectado,),
                            daemon=True
                        ).start()
                        time.sleep(COOLDOWN)              # Pausa para evitar ativação dupla
                    else:
                        log("Comando não reconhecido", "aviso")
                        falar("Não entendi o comando. Diga max ajuda para ver os comandos disponíveis")

            except sr.UnknownValueError:
                pass                                      # Áudio não reconhecível = silêncio ou ruído
            except sr.RequestError:
                log("Erro de conexão com Google Speech", "erro")
                falar("Estou sem conexão com o servidor de voz. Verifique a internet")
                time.sleep(5)                             # Aguarda antes de tentar de novo

        except Exception as e:
            log(f"Erro no detector de voz: {e}", "erro")
            time.sleep(1)                                 # Pausa breve antes de recomeçar

# ═══════════════════════════════════════════════════════════════════════════
# 🖥️ INTERFACE GRÁFICA — MAX BOT UI
# ═══════════════════════════════════════════════════════════════════════════
class MaxBotApp:
    """
    Janela principal do Max Bot com interface gráfica tkinter.
    Exibe status dos detectores, log de atividades e controles.
    Tema: industrial dark (preto/verde neon) — estilo terminal hacker.
    """

    # --- PALETA DE CORES ---
    BG          = "#0a0a0f"     # Preto profundo (fundo principal)
    BG2         = "#111118"     # Preto ligeiramente mais claro (painéis)
    BG3         = "#1a1a24"     # Cinza escuro (cards e agrupamentos)
    ACCENT      = "#00ff88"     # Verde neon (cor de destaque principal)
    ACCENT2     = "#00ccff"     # Ciano neon (cor de destaque secundária)
    ACCENT3     = "#ff6b35"     # Laranja neon (alertas e avisos)
    TEXT        = "#e0e0e8"     # Branco suave (texto principal)
    TEXT_DIM    = "#606070"     # Cinza médio (texto secundário/inativo)
    BORDER      = "#2a2a3a"     # Cinza escuro (bordas dos painéis)
    SUCCESS     = "#00ff88"     # Verde (mensagens de sucesso)
    ERROR       = "#ff4444"     # Vermelho (mensagens de erro)
    WARNING     = "#ffaa00"     # Âmbar (avisos)
    VOICE_CLR   = "#00ccff"     # Ciano (mensagens de voz)
    CLAP_CLR    = "#ff6b35"     # Laranja (detecções de palma)
    CMD_CLR     = "#c084fc"     # Lilás (comandos executados)

    def __init__(self, root):
        """
        Construtor da interface. Configura janela, widgets e inicia loops de atualização.
        root: instância do Tk() passada ao criar a aplicação.
        """
        self.root = root                         # Referência à janela raiz do tkinter
        self.running = False                     # Flag: detectores estão rodando?
        self.calibrating = False                 # Flag: calibração em andamento?
        self.clap_count_display = 0             # Contador de palmas para exibição

        self._setup_window()                     # Configura propriedades da janela
        self._build_ui()                         # Constrói todos os widgets
        self._start_queue_polling()              # Inicia leitura das filas de mensagens

    def _setup_window(self):
        """Configura título, tamanho, cor de fundo e ícone da janela principal."""
        self.root.title("MAX BOT — Sistema de Automação por Palmas e Voz")
        self.root.geometry("900x680")            # Largura x Altura inicial da janela
        self.root.minsize(800, 580)              # Tamanho mínimo permitido
        self.root.configure(bg=self.BG)          # Cor de fundo da janela
        self.root.resizable(True, True)          # Permite redimensionar

        # Tenta definir ícone (pode falhar se .ico não existir)
        try:
            self.root.iconbitmap("max_bot.ico")
        except Exception:
            pass

    def _build_ui(self):
        """Constrói toda a interface gráfica dividida em seções."""
        self._build_header()    # Cabeçalho com nome e versão
        self._build_status()    # Painel de status dos detectores
        self._build_controls()  # Botões de controle
        self._build_log()       # Área de log de atividades
        self._build_footer()    # Rodapé com dica de comandos

    # -----------------------------------------------------------------------
    # CABEÇALHO
    # -----------------------------------------------------------------------
    def _build_header(self):
        """Cria o cabeçalho da janela com logo ASCII art e versão."""
        header = tk.Frame(self.root, bg=self.BG, pady=12)
        header.pack(fill=tk.X, padx=20)          # Ocupa toda a largura com margens

        # Linha decorativa superior
        tk.Frame(header, bg=self.ACCENT, height=2).pack(fill=tk.X)

        # Container interno do cabeçalho
        inner = tk.Frame(header, bg=self.BG)
        inner.pack(fill=tk.X, pady=(8, 4))

        # Título principal
        tk.Label(
            inner,
            text="◈ MAX BOT",                    # Texto do título com símbolo decorativo
            font=("Courier New", 28, "bold"),     # Fonte monospace para estética terminal
            fg=self.ACCENT,                        # Verde neon
            bg=self.BG
        ).pack(side=tk.LEFT)

        # Subtítulo e versão (lado direito)
        info_frame = tk.Frame(inner, bg=self.BG)
        info_frame.pack(side=tk.RIGHT)

        tk.Label(
            info_frame,
            text="SISTEMA DE AUTOMAÇÃO v2.0",
            font=("Courier New", 9),
            fg=self.TEXT_DIM,
            bg=self.BG
        ).pack(anchor=tk.E)

        tk.Label(
            info_frame,
            text="👏 Palmas + 🎤 Voz",           # Indicador dos dois modos de ativação
            font=("Courier New", 11),
            fg=self.ACCENT2,
            bg=self.BG
        ).pack(anchor=tk.E)

        # Linha decorativa inferior do cabeçalho
        tk.Frame(header, bg=self.BORDER, height=1).pack(fill=tk.X, pady=(6, 0))

    # -----------------------------------------------------------------------
    # PAINEL DE STATUS
    # -----------------------------------------------------------------------
    def _build_status(self):
        """Cria os cards de status mostrando estado de cada componente do bot."""
        container = tk.Frame(self.root, bg=self.BG, padx=20)
        container.pack(fill=tk.X, pady=(8, 0))

        # Label da seção
        tk.Label(
            container,
            text="[ STATUS DO SISTEMA ]",
            font=("Courier New", 9),
            fg=self.TEXT_DIM,
            bg=self.BG
        ).pack(anchor=tk.W, pady=(0, 6))

        cards_frame = tk.Frame(container, bg=self.BG)
        cards_frame.pack(fill=tk.X)

        # Define os 4 cards de status: (id, label, ícone)
        self.status_labels = {}       # Dicionário para acessar labels de status
        self.status_dots = {}         # Dicionário para acessar indicadores (pontos)

        status_items = [
            ("bot",     "BOT",        "◉"),   # Status geral do bot
            ("palmas",  "PALMAS",     "👏"),   # Detector de palmas
            ("voz",     "VOZ",        "🎤"),   # Detector de voz
            ("volume",  "VOLUME",     "🔊"),   # Controle de volume
        ]

        for sid, label, icon in status_items:
            card = tk.Frame(cards_frame, bg=self.BG3,
                           relief=tk.FLAT, bd=0,
                           highlightbackground=self.BORDER,
                           highlightthickness=1)
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), pady=2)

            inner = tk.Frame(card, bg=self.BG3, padx=10, pady=8)
            inner.pack(fill=tk.BOTH)

            # Linha do ícone + ponto colorido
            top = tk.Frame(inner, bg=self.BG3)
            top.pack(fill=tk.X)

            tk.Label(top, text=icon, font=("Segoe UI Emoji", 14),
                     bg=self.BG3).pack(side=tk.LEFT)

            # Ponto indicador de status (verde = ativo, cinza = inativo)
            dot = tk.Label(top, text="●", font=("Courier New", 14),
                          fg=self.TEXT_DIM, bg=self.BG3)
            dot.pack(side=tk.RIGHT)
            self.status_dots[sid] = dot   # Salva referência para atualizar depois

            # Label do nome do componente
            lbl = tk.Label(inner, text=label, font=("Courier New", 9, "bold"),
                          fg=self.TEXT_DIM, bg=self.BG3)
            lbl.pack(anchor=tk.W)
            self.status_labels[sid] = lbl  # Salva referência para atualizar depois

        # Inicializa status do volume baseado em disponibilidade do pycaw
        if VOLUME_AVAILABLE:
            self._set_status_card("volume", True, "DISPONÍVEL")
        else:
            self._set_status_card("volume", False, "INDISPONÍVEL")

    def _set_status_card(self, sid, ativo, texto=None):
        """
        Atualiza visualmente um card de status.
        sid: identificador do card
        ativo: True = verde (ativo), False = cinza (inativo)
        texto: texto opcional para exibir
        """
        cor = self.ACCENT if ativo else self.TEXT_DIM      # Verde se ativo, cinza se não
        self.status_dots[sid].configure(fg=cor)             # Atualiza cor do ponto indicador
        if texto:
            self.status_labels[sid].configure(text=texto, fg=cor)  # Atualiza texto e cor

    # -----------------------------------------------------------------------
    # BOTÕES DE CONTROLE
    # -----------------------------------------------------------------------
    def _build_controls(self):
        """Cria os botões de controle do bot (iniciar, calibrar, comandos manuais)."""
        container = tk.Frame(self.root, bg=self.BG, padx=20)
        container.pack(fill=tk.X, pady=(12, 0))

        tk.Label(
            container,
            text="[ CONTROLES ]",
            font=("Courier New", 9),
            fg=self.TEXT_DIM,
            bg=self.BG
        ).pack(anchor=tk.W, pady=(0, 6))

        # Frame dos botões principais
        btns = tk.Frame(container, bg=self.BG)
        btns.pack(fill=tk.X)

        # Configuração dos botões: (texto, ação, cor_fundo, cor_texto)
        main_buttons = [
            ("▶ INICIAR",     self._iniciar,     self.ACCENT,  self.BG),
            ("⏹ PARAR",       self._parar,        self.ERROR,   "#fff"),
            ("👏 CALIBRAR",   self._calibrar,     self.ACCENT3, "#fff"),
            ("🗑 LIMPAR LOG",  self._limpar_log,   self.BG3,     self.TEXT),
        ]

        for text, cmd, bg, fg in main_buttons:
            tk.Button(
                btns,
                text=text,
                command=cmd,                                # Função chamada ao clicar
                font=("Courier New", 10, "bold"),
                bg=bg, fg=fg,                               # Cores do botão
                activebackground=self.BG2,                  # Cor ao pressionar
                activeforeground=self.ACCENT,
                relief=tk.FLAT,                             # Sem relevo (flat design)
                padx=16, pady=8,
                cursor="hand2",                             # Cursor de mão ao passar
                bd=0
            ).pack(side=tk.LEFT, padx=(0, 6))

        # Separador visual
        tk.Frame(container, bg=self.BORDER, height=1).pack(fill=tk.X, pady=(10, 6))

        # Label da seção de comandos manuais
        tk.Label(
            container,
            text="[ COMANDOS MANUAIS ]",
            font=("Courier New", 9),
            fg=self.TEXT_DIM,
            bg=self.BG
        ).pack(anchor=tk.W, pady=(0, 6))

        # Frame dos botões de comando rápido
        cmd_frame = tk.Frame(container, bg=self.BG)
        cmd_frame.pack(fill=tk.X)

        # Botões que disparam comandos diretamente
        quick_commands = [
            ("💼 Trabalho",    "modo_trabalho"),
            ("🌐 Chrome",      "abrir_chrome"),
            ("🕐 Hora",        "falar_hora"),
            ("📅 Data",        "falar_data"),
            ("📝 Notepad",     "abrir_notepad"),
            ("🔊 Vol +",       "aumentar_volume"),
            ("🔉 Vol -",       "diminuir_volume"),
            ("⏹ Música",      "parar_musica"),
            ("❓ Ajuda",       "ajuda"),
        ]

        for text, cmd_name in quick_commands:
            btn = tk.Button(
                cmd_frame,
                text=text,
                command=lambda c=cmd_name: self._executar_manual(c),  # Lambda captura cmd_name
                font=("Courier New", 9),
                bg=self.BG3,
                fg=self.TEXT,
                activebackground=self.BG2,
                activeforeground=self.ACCENT,
                relief=tk.FLAT,
                padx=10, pady=6,
                cursor="hand2",
                bd=0,
                highlightbackground=self.BORDER,
                highlightthickness=1
            )
            btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)   # Empilha horizontalmente

    def _executar_manual(self, cmd_nome):
        """Executa um comando manualmente via botão da interface (em thread separada)."""
        threading.Thread(
            target=executar_comando,
            args=(cmd_nome,),
            daemon=True                         # Thread daemon: encerra com o programa
        ).start()

    # -----------------------------------------------------------------------
    # ÁREA DE LOG
    # -----------------------------------------------------------------------
    def _build_log(self):
        """Cria a área de log com texto rolável para exibir atividades em tempo real."""
        container = tk.Frame(self.root, bg=self.BG, padx=20)
        container.pack(fill=tk.BOTH, expand=True, pady=(12, 0))  # expand=True: ocupa espaço restante

        # Cabeçalho do log com indicador de atividade piscante
        header = tk.Frame(container, bg=self.BG)
        header.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            header,
            text="[ LOG DE ATIVIDADES ]",
            font=("Courier New", 9),
            fg=self.TEXT_DIM,
            bg=self.BG
        ).pack(side=tk.LEFT)

        # Indicador pulsante de "gravando/ativo"
        self.live_indicator = tk.Label(
            header,
            text="● LIVE",
            font=("Courier New", 9),
            fg=self.ERROR,
            bg=self.BG
        )
        self.live_indicator.pack(side=tk.RIGHT)

        # Frame do log com borda colorida
        log_frame = tk.Frame(
            container,
            bg=self.BORDER,
            padx=1, pady=1      # Cria efeito de borda com 1px de espessura
        )
        log_frame.pack(fill=tk.BOTH, expand=True)

        # Widget de texto com rolagem para exibir o log
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            font=("Courier New", 10),   # Fonte monospace para estética de terminal
            bg=self.BG2,                 # Fundo levemente mais claro que o principal
            fg=self.TEXT,                # Cor do texto padrão
            insertbackground=self.ACCENT, # Cor do cursor de inserção
            selectbackground=self.BG3,   # Cor de seleção de texto
            relief=tk.FLAT,              # Sem relevo
            wrap=tk.WORD,                # Quebra linha em palavras completas
            state=tk.DISABLED,           # Somente leitura (usuário não pode editar)
            padx=10, pady=8
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Define tags de cor para cada tipo de mensagem no log
        self.log_text.tag_configure("timestamp", foreground=self.TEXT_DIM)  # Hora em cinza
        self.log_text.tag_configure("info",      foreground=self.TEXT)       # Info em branco
        self.log_text.tag_configure("sucesso",   foreground=self.SUCCESS)    # Sucesso em verde
        self.log_text.tag_configure("erro",      foreground=self.ERROR)      # Erro em vermelho
        self.log_text.tag_configure("aviso",     foreground=self.WARNING)    # Aviso em âmbar
        self.log_text.tag_configure("voz",       foreground=self.VOICE_CLR)  # Voz em ciano
        self.log_text.tag_configure("palma",     foreground=self.CLAP_CLR)   # Palma em laranja
        self.log_text.tag_configure("comando",   foreground=self.CMD_CLR)    # Comando em lilás

    def _append_log(self, timestamp, mensagem, tipo):
        """
        Adiciona uma linha ao widget de log com formatação colorida.
        Desabilita/habilita o widget para modificar o conteúdo (somente leitura).
        """
        self.log_text.configure(state=tk.NORMAL)     # Habilita edição temporariamente
        self.log_text.insert(tk.END, f"[{timestamp}] ", "timestamp")  # Insere hora com cor
        self.log_text.insert(tk.END, f"{mensagem}\n", tipo)            # Insere mensagem com cor do tipo
        self.log_text.configure(state=tk.DISABLED)   # Bloqueia edição novamente
        self.log_text.see(tk.END)                    # Rola para o final automaticamente

    def _limpar_log(self):
        """Limpa todo o conteúdo da área de log."""
        self.log_text.configure(state=tk.NORMAL)      # Habilita edição
        self.log_text.delete(1.0, tk.END)              # Remove tudo (linha 1 ao fim)
        self.log_text.configure(state=tk.DISABLED)    # Bloqueia novamente
        log("Log limpo", "info")                       # Registra a limpeza

    # -----------------------------------------------------------------------
    # RODAPÉ
    # -----------------------------------------------------------------------
    def _build_footer(self):
        """Cria rodapé com dicas de comandos de voz disponíveis."""
        footer = tk.Frame(self.root, bg=self.BG2, pady=8)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        # Linha decorativa superior do rodapé
        tk.Frame(footer, bg=self.BORDER, height=1).pack(fill=tk.X)

        inner = tk.Frame(footer, bg=self.BG2)
        inner.pack(pady=(6, 0))

        tk.Label(
            inner,
            text='💡 Diga: "max bora trabalhar" | "max que horas são" | "max abre chrome" | "max ajuda"',
            font=("Courier New", 9),
            fg=self.TEXT_DIM,
            bg=self.BG2
        ).pack()

    # -----------------------------------------------------------------------
    # CONTROLES PRINCIPAIS
    # -----------------------------------------------------------------------
    def _iniciar(self):
        """Inicia os detectores de palmas e voz em threads separadas."""
        if self.running:                                    # Não inicia se já estiver rodando
            log("Bot já está ativo!", "aviso")
            return

        self.running = True
        self._set_status_card("bot", True, "ATIVO")        # Atualiza card de status

        # Inicia thread do detector de palmas
        threading.Thread(target=clap_detector, daemon=True).start()
        time.sleep(0.5)                                     # Pequena pausa entre inicializações

        # Inicia thread do detector de voz
        threading.Thread(target=speech_detector, daemon=True).start()

        play_listening_sound()                              # Bipes de confirmação
        log("═" * 50, "info")
        log("✅ MAX BOT INICIADO — Aguardando comandos...", "sucesso")
        log("═" * 50, "info")
        falar("Max Bot iniciado e pronto para receber comandos")

    def _parar(self):
        """Para os detectores (requer reinício do programa para reativar)."""
        self.running = False
        self._set_status_card("bot", False, "PARADO")
        self._set_status_card("palmas", False, "PARADO")
        self._set_status_card("voz", False, "PARADO")
        log("⏹ Bot pausado. Reinicie o programa para reativar.", "aviso")
        falar("Bot pausado. Reinicie o programa para reativar os detectores")

    def _calibrar(self):
        """Inicia o processo de calibração de palmas em thread separada."""
        if self.calibrating:                               # Evita calibração dupla
            return

        self.calibrating = True
        log("━" * 50, "info")
        log("👏 CALIBRAÇÃO INICIADA", "aviso")
        log("Bata as palmas quando solicitado...", "info")

        def _run_calibration():
            """Executa calibração e atualiza fingerprint global."""
            global clap_fingerprint
            try:
                # Passa log() como callback para calibração enviar mensagens à interface
                fp = calibrate_claps(callback_log=lambda m: log(m, "palma"))
                clap_fingerprint = fp                      # Atualiza fingerprint global
                log("✅ Calibração salva com sucesso!", "sucesso")
                falar("Calibração concluída! Agora posso reconhecer suas palmas.")
            except Exception as e:
                log(f"Erro na calibração: {e}", "erro")
                falar("Ocorreu um erro durante a calibração")
            finally:
                self.calibrating = False                   # Libera flag de calibração

        threading.Thread(target=_run_calibration, daemon=True).start()

    # -----------------------------------------------------------------------
    # LOOP DE ATUALIZAÇÃO DA INTERFACE (POLLING DE FILAS)
    # -----------------------------------------------------------------------
    def _start_queue_polling(self):
        """Inicia o ciclo de verificação das filas de mensagens a cada 50ms."""
        self._poll_queues()          # Primeira verificação imediata
        self._animate_indicator()    # Inicia animação do indicador LIVE

    def _poll_queues(self):
        """
        Verifica e processa todas as mensagens nas filas (log e status).
        Chamado repetidamente pelo tkinter via after() a cada 50ms.
        As filas são a ponte entre as threads de detecção e a interface gráfica.
        """
        # Processa todas as mensagens de log disponíveis
        while not log_queue.empty():
            try:
                timestamp, mensagem, tipo = log_queue.get_nowait()  # Pega sem bloquear
                self._append_log(timestamp, mensagem, tipo)         # Exibe na interface
            except queue.Empty:
                break                                               # Fila esvaziou

        # Processa atualizações de status
        while not status_queue.empty():
            try:
                status_id, ativo = status_queue.get_nowait()
                self._set_status_card(status_id, ativo)            # Atualiza card visual
            except queue.Empty:
                break

        # Reagenda esta função para rodar novamente em 50ms
        self.root.after(50, self._poll_queues)

    def _animate_indicator(self):
        """Faz o indicador '● LIVE' piscar alterando sua cor periodicamente."""
        current = self.live_indicator.cget("fg")          # Obtém cor atual do indicador
        new_color = self.ERROR if current == self.BG else self.ERROR  # Alterna cores
        # Pisca entre vermelho brilhante e vermelho escuro
        new_color = "#ff2222" if current == "#660000" else "#660000"
        self.live_indicator.configure(fg=new_color)        # Aplica nova cor
        self.root.after(600, self._animate_indicator)      # Reagenda em 600ms

# ───────────────────────────────────────────────────────────────────────────
# 🚀 FUNÇÃO PRINCIPAL — PONTO DE ENTRADA DO PROGRAMA
# ───────────────────────────────────────────────────────────────────────────
def main():
    """
    Função main: inicializa a interface gráfica e carrega perfil de palmas.
    Se iniciado com --calibrar, força nova calibração antes de abrir a interface.
    """
    global clap_fingerprint            # Usa a variável global de fingerprint

    # Tenta carregar perfil de palmas existente do arquivo JSON
    clap_fingerprint = load_clap_profile()

    # Verifica se o usuário quer forçar re-calibração via argumento de linha de comando
    fc = "--calibrar" in sys.argv or "--calibrate" in sys.argv
    if fc:
        print("Modo calibração forçada via argumento de linha de comando")
        clap_fingerprint = None        # Remove perfil existente para forçar recalibração

    # Cria janela raiz do tkinter
    root = tk.Tk()

    # Instancia a aplicação (constrói toda a interface)
    app = MaxBotApp(root)

    # Mensagem de boas-vindas no log ao iniciar
    app._append_log(
        datetime.now().strftime("%H:%M:%S"),
        "════════════════════════════════════════════════════",
        "sucesso"
    )
    app._append_log(
        datetime.now().strftime("%H:%M:%S"),
        "◈ MAX BOT v2.0 — Sistema de Automação Inicializado",
        "sucesso"
    )
    app._append_log(
        datetime.now().strftime("%H:%M:%S"),
        "════════════════════════════════════════════════════",
        "sucesso"
    )

    # Informa sobre o perfil de palmas carregado (ou ausência)
    if clap_fingerprint is not None:
        app._append_log(
            datetime.now().strftime("%H:%M:%S"),
            "✅ Perfil de palmas carregado. Pressione INICIAR para começar.",
            "sucesso"
        )
    else:
        app._append_log(
            datetime.now().strftime("%H:%M:%S"),
            "⚠️ Nenhum perfil encontrado. Clique em CALIBRAR antes de iniciar.",
            "aviso"
        )

    # Se forçou calibração, a dispara automaticamente após 1 segundo
    if fc:
        root.after(1000, app._calibrar)   # Agenda calibração para após a janela abrir

    play_startup_sound()               # Toca som de inicialização do sistema

    # Configura o comportamento ao fechar a janela (X)
    def on_closing():
        """Chamado quando o usuário fecha a janela."""
        falar("Até logo!")             # Despede por voz
        root.destroy()                 # Destrói a janela e encerra o tkinter
        sys.exit(0)                    # Garante encerramento completo do processo

    root.protocol("WM_DELETE_WINDOW", on_closing)  # Registra handler de fechamento

    root.mainloop()                    # Inicia o loop principal do tkinter (bloqueante)

# ───────────────────────────────────────────────────────────────────────────
# PONTO DE ENTRADA: só executa main() se rodado diretamente (não importado)
# ───────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()                             # Chama a função principal do programa

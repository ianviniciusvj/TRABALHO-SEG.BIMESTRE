import paho.mqtt.client as mqtt
import json
import random
import time
import hashlib
import threading
import sys

BROKER_HOST = "broker.emqx.io"
BROKER_PORT = 1883

if len(sys.argv) >= 2:
    NUM_PARTICIPANTS = int(sys.argv[1])
else:
    NUM_PARTICIPANTS = 3

client = None

client_id = random.randint(0, 65335)
known_clients = set()
init_done_event = threading.Event()

votes = {}
leader_client_id = None
i_am_leader = False

transaction_table = {}

current_challenge_id = None
current_challenge_value = None
stop_mining_flag = threading.Event()

def log(msg):
    print(f"[Client {client_id}] {msg}", flush=True)

def json_publish(topic, payload_dict):
    payload_str = json.dumps(payload_dict)
    client.publish(topic, payload_str)

def on_connect(cli, userdata, flags, rc):
    if rc == 0:
        log("Conectado ao broker MQTT.")
        cli.subscribe("sd/init")
        cli.subscribe("sd/voting")
        cli.subscribe("sd/challenge")
        cli.subscribe("sd/solution")
        cli.subscribe("sd/result")
    else:
        log(f"Falha na conexão. Código de retorno = {rc}")

def on_message(cli, userdata, msg):
    topic = msg.topic
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except:
        return

    if topic == "sd/init":
        handle_init_msg(payload)
    elif topic == "sd/voting":
        handle_voting_msg(payload)
    elif topic == "sd/challenge":
        handle_challenge_msg(payload)
    elif topic == "sd/solution":
        handle_solution_msg(payload)
    elif topic == "sd/result":
        handle_result_msg(payload)

def handle_init_msg(payload):
    other_id = payload.get("ClientID")
    if other_id is None:
        return

    if other_id not in known_clients:
        known_clients.add(other_id)
        log(f"InitMsg recebido de {other_id}. Total conhecidos: {len(known_clients)}")

    if len(known_clients) >= NUM_PARTICIPANTS:
        init_done_event.set()

def handle_voting_msg(payload):
    cid = payload.get("ClientID")
    vote = payload.get("VoteID")

    if cid is None or vote is None:
        return

    if cid not in votes:
        votes[cid] = vote
        log(f"Vote recebido: ClientID={cid}, VoteID={vote}. Total de votos: {len(votes)}")

def handle_challenge_msg(payload):
    global current_challenge_id, current_challenge_value

    tx_id = payload.get("TransactionID")
    challenge = payload.get("Challenge")

    if tx_id is None or challenge is None:
        return

    log(f"Challenge recebido: TransactionID={tx_id}, Challenge={challenge}")

    transaction_table[tx_id] = {
        "challenge": challenge,
        "solution": None,
        "winner": -1
    }

    current_challenge_id = tx_id
    current_challenge_value = challenge
    stop_mining_flag.clear()

def handle_solution_msg(payload):
    if not i_am_leader:
        return

    tx_id = payload.get("TransactionID")
    sol = payload.get("Solution")
    sol_client_id = payload.get("ClientID")

    if tx_id is None or sol is None or sol_client_id is None:
        return

    if tx_id not in transaction_table:
        return

    tx_entry = transaction_table[tx_id]

    if tx_entry["winner"] != -1:
        return

    challenge = tx_entry["challenge"]

    if is_valid_solution(tx_id, challenge, sol):
        log(f"Solução VÁLIDA recebida de {sol_client_id} para TransactionID {tx_id}")
        tx_entry["solution"] = sol
        tx_entry["winner"] = sol_client_id
        json_publish("sd/result", {
            "ClientID": sol_client_id,
            "TransactionID": tx_id,
            "Solution": sol,
            "Result": 1
        })
    else:
        log(f"Solução INVÁLIDA de {sol_client_id} para TransactionID {tx_id}")
        json_publish("sd/result", {
            "ClientID": sol_client_id,
            "TransactionID": tx_id,
            "Solution": sol,
            "Result": 0
        })

def handle_result_msg(payload):
    tx_id = payload.get("TransactionID")
    res = payload.get("Result")
    winning_client = payload.get("ClientID")

    if tx_id is None or res is None or winning_client is None:
        return

    if tx_id not in transaction_table:
        transaction_table[tx_id] = {
            "challenge": None,
            "solution": None,
            "winner": -1
        }

    tx_entry = transaction_table[tx_id]

    if res != 0:
        log(f"Resultado: TransactionID={tx_id} ACEITA. Winner = {winning_client}")
        tx_entry["winner"] = winning_client
        stop_mining_flag.set()
    else:
        log(f"Resultado: TransactionID={tx_id} REJEITADA para ClientID={winning_client}")

def phase_init():
    known_clients.add(client_id)
    log(f"Iniciando fase INIT com ClientID={client_id}, esperando {NUM_PARTICIPANTS} participantes.")

    def send_init_loop():
        while not init_done_event.is_set():
            json_publish("sd/init", {"ClientID": client_id})
            time.sleep(2)

    threading.Thread(target=send_init_loop, daemon=True).start()
    init_done_event.wait()
    log("Fase INIT concluída. Todos os participantes conhecidos.")

def phase_election():
    global leader_client_id, i_am_leader

    vote_id = random.randint(0, 65335)
    log(f"Iniciando fase ELECTION. Meu VoteID={vote_id}")

    votes[client_id] = vote_id
    log(f"Vote recebido (local): ClientID={client_id}, VoteID={vote_id}. Total de votos: {len(votes)}")

    payload = {
        "ClientID": client_id,
        "VoteID": vote_id
    }

    time.sleep(0.8)
    json_publish("sd/voting", payload)

    deadline = time.time() + 8.0
    while time.time() < deadline and len(votes) < NUM_PARTICIPANTS:
        time.sleep(0.2)

    log(f"Total de votos ao final da espera: {len(votes)}")

    if len(votes) == 0:
        log("Nenhum voto recebido. Não é possível eleger líder.")
        return

    leader_client_id, leader_vote = max(
        votes.items(),
        key=lambda item: (item[1], item[0])
    )

    log(f"Líder eleito: ClientID={leader_client_id}, VoteID={leader_vote}")

    if leader_client_id == client_id:
        i_am_leader = True
        log("Eu sou o LÍDER (Controlador).")
    else:
        log("Eu sou MINERADOR.")

def controller_loop():
    tx_id = 0
    challenge = random.randint(1, 20)

    log(f"Gerando desafio: TransactionID={tx_id}, Challenge={challenge}")

    transaction_table[tx_id] = {
        "challenge": challenge,
        "solution": None,
        "winner": -1
    }

    json_publish("sd/challenge", {
        "TransactionID": tx_id,
        "Challenge": challenge
    })

    log("Desafio publicado. Aguardando soluções...")

    while True:
        time.sleep(5)

def is_valid_solution(tx_id, challenge, solution_str):
    base = f"{tx_id}:{solution_str}"
    sha1_hash = hashlib.sha1(base.encode("utf-8")).hexdigest()
    zeros_required = max(1, challenge // 4)
    return sha1_hash.startswith("0" * zeros_required)

def miner_loop():
    log("Entrando no loop de MINERADOR. Aguardando challenge...")

    while current_challenge_id is None or current_challenge_value is None:
        time.sleep(1)

    log(f"Iniciando mineração para TransactionID={current_challenge_id}, Challenge={current_challenge_value}")

    tx_id = current_challenge_id
    challenge = current_challenge_value

    attempt = 0
    while not stop_mining_flag.is_set():
        solution_candidate = f"sol_{client_id}_{attempt}"

        if is_valid_solution(tx_id, challenge, solution_candidate):
            log(f"Encontrei solução: {solution_candidate}")
            json_publish("sd/solution", {
                "ClientID": client_id,
                "TransactionID": tx_id,
                "Solution": solution_candidate
            })
            time.sleep(3)

        attempt += 1

    log("Mineração encerrada.")

def main():
    global client

    log(f"Inicializando nó com NUM_PARTICIPANTS={NUM_PARTICIPANTS}")

    client = mqtt.Client(client_id=f"node_{client_id}_{random.randint(1,999999)}", clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER_HOST, BROKER_PORT, 60)
    client.loop_start()

    phase_init()
    phase_election()

    if i_am_leader:
        controller_loop()
    else:
        miner_loop()

if __name__ == "__main__":
    main()
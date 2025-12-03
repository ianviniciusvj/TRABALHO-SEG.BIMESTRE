README – Sistema Distribuído com MQTT (LAB III – Programação Paralela e Distribuída)
Descrição

Este projeto implementa um sistema distribuído utilizando comunicação indireta com MQTT.
Ele é composto por três fases principais:

Fase INIT: descobre os participantes

Fase ELECTION: escolhe automaticamente o coordenador (líder)

Fase CHALLENGE / SOLUTION / RESULT: execução da Prova de Trabalho entre líder e mineradores

O sistema pode atuar simultaneamente como:

Nó participante

Controlador (caso seja eleito líder)

Minerador

Todos os processos se comunicam via tópicos MQTT.

Dependências

Python 3.x

paho-mqtt

hashlib (nativo)

threading (nativo)

Para instalar o paho-mqtt:

pip install paho-mqtt

Como executar

Abra 3 terminais na pasta do projeto e execute em cada um:

python node.py 3


Onde 3 é o número total de participantes.

Fluxo de execução
1. INIT

Cada nó publica sua presença em sd/init até reconhecer todos os participantes.

2. ELEIÇÃO

Cada nó gera um VoteID

Registra seu próprio voto localmente

Publica seu voto em sd/voting

Aguarda até 8 segundos por votos dos outros

O maior VoteID vence (desempate por maior ClientID)

3. PAPEL DO LÍDER

Cria TransactionID e Challenge

Publica desafio em sd/challenge

Valida soluções enviadas pelos mineradores

Publica resultado em sd/result

4. PAPEL DOS MINERADORES

Recebem o desafio

Tentam encontrar uma solução válida usando SHA-1

Ao encontrar, enviam para sd/solution

Param quando o resultado é publicado

Tópicos MQTT utilizados
Tópico	Função
sd/init	Descoberta de participantes
sd/voting	Troca de votos da eleição
sd/challenge	Envio do desafio criptográfico
sd/solution	Soluções propostas pelos nós
sd/result	Resultado final da mineração
Observações

Este projeto utiliza o broker público EMQX, sujeito a atrasos ou perda de mensagens.
Para garantir robustez:

o voto próprio é contabilizado localmente

a eleição utiliza timeout de 8 segundos
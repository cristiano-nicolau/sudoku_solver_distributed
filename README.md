# cd_sudoku
Projeto CD 2023/24

## Instruções de execução

Para correr o programa, é necessário ter o Python 3 instalado.

Podemos lançar o número de nós que quisermos, e cada nó pode ser lançado com um argumento que indica o endereço de outro nó ao qual se quer conectar.

```bash
python3 node.py -p 8001 -s 7001 -a localhost:7000 -h 1
python3 node.py -p 8002 -s 7002 -a localhost:7000 -h 1
python3 node.py -p 8003 -s 7003 -a localhost:7000 -h 1
python3 node.py -p 8000 -s 7000 -h 1
```

Para fazer os testes, podemos correr os seguintes comandos:

```bash
curl http://localhost:8000/solve -X POST -H 'Content-Type: application/json' -d '{"sudoku": [[0, 0, 0, 1, 0, 0, 0, 0, 0], [0, 0, 0, 3, 2, 0, 0, 0, 0], [0, 0, 0, 0, 0, 9, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 7, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 9, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 9, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 3], [0, 0, 0, 0, 0, 0, 0, 0, 0]]}'
curl http://localhost:8000/stats -X GET
curl http://localhost:8000/network -X GET
```

## Descrição do projeto

O projeto consiste num sistema distribuído de resolução de sudokus. Cada peer tem uma interface HTTP que permite receber pedidos HTTP, e uma interface UDP que permite comunicar com outros peers. Os nós comunicam entre si através de sockets UDP, e a comunicação é feita através de mensagens JSON. Qualquer um dos nós pode receber pedidos HTTP. O nó que recebe o pedido HTTP de `solve`, no caso de estar conectado a outros peers, funciona como um nó master, distribuindo as posições a serem resolvidas pelos outros peers, e depois junta as soluções e devolve a resposta ao cliente que fez o pedido HTTP. No caso do nó estar sozinho, ele resolve o sudoku e devolve a resposta ao cliente que fez o pedido HTTP.

## Comunicação entre os nós e pedidos HTTP

As mensagens JSON são compostas por um campo "type" que indica o tipo de mensagem, e um campo "address" que indica o endereço do nó que enviou a mensagem. Os tipos de mensagens são os seguintes:

### Conexão:
- `connect` -> mensagem enviada quando um nó se quer conectar a outro nó.
- `connected` -> mensagem enviada como resposta à mensagem `connect`, indicando que a conexão foi bem-sucedida.
- `disconnect` -> mensagem enviada quando um nó se quer desconectar de outro nó.
- `all_peers` -> mensagem enviada sempre que existe uma nova conexão, com a lista de todos os nós conectados a outros nós, para que todos os nós saibam os nós existentes na rede.

### Sudoku:
- `solve` -> mensagem enviada com a posição do sudoku a ser resolvida.
- `solution` -> mensagem enviada com a solução de uma posição do sudoku.
- `stats` -> mensagem enviada a indicar as estatísticas do nó que enviou a mensagem. Esta mensagem está sempre a ser trocada de forma a que todos os nós tenham as estatísticas atualizadas sobre todos os nós.

### Pedidos HTTP:
- `/solve` -> recebe um JSON com o sudoku a ser resolvido, e devolve a solução do sudoku.
- `/stats` -> devolve as estatísticas de toda a rede desde que a rede foi iniciada.
- `/network` -> devolve a lista de todos os nós conectados neste momento na rede.

## Sistema P2P Descentralizado
Este projeto é baseado numa arquitetura peer-to-peer (P2P) descentralizada. Num sistema P2P, os nós comunicam diretamente uns com os outros sem depender de um servidor central. Cada nó pode executar tarefas e compartilhar informações com outros nós, tornando o sistema mais resiliente e escalável. A comunicação entre os nós é realizada utilizando o protocolo UDP (User Datagram Protocol) para garantir baixa latência e eficiência na troca de mensagens. Quando múltiplos peers estão presentes, um peer assume o papel de distribuidor de tarefas. Este peer coordenador envia e recebe mensagens de outros peers enquanto também contribui para o processo de resolução do Sudoku.

## Arquitetura do Sistema
O nosso sistema divide a tarefa de resolver o Sudoku entre múltiplos peers. Cada nó peer pode aceitar pedidos para resolver puzzles de Sudoku via sua interface HTTP. O sistema distribui dinamicamente partes do puzzle para diferentes peers encontrarem a solução de maneira eficiente. Os peers comunicam-se usando um protocolo P2P customizado para trocar informações e atualizações.

## Node.py
O script `node.py` é responsável pela funcionalidade principal de cada peer na rede.

### Funções principais incluem:
- Inicializar o nó e conectar-se à rede.
- Manipular mensagens e pedidos recebidos de outros nós.
- Distribuir tarefas entre os peers disponíveis e processar soluções.
- Transmitir atualizações e estatísticas para outros peers.
- Gerenciar a fila de tarefas e garantir que cada parte do puzzle seja resolvida.
- Manipular falhas dos nós e ajustar dinamicamente a rede.

## Protocolo
O protocolo customizado P2P em nosso projeto inclui os seguintes passos:

| Objetivo                 | Destino       | Mensagem                                                                                                                                                   | Resposta                                                                                                                                                                   |
|--------------------------|---------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Connect to a Node        | Qualquer nó   | `{"type": "connect", "address": f"{host}:{port}"}`                                                                                                          | `{"type": "connected", "address": f"{host}:{port}"}`                                                                                                                       |
| Acknowledge Connection   | Qualquer nó   | `{"type": "connected", "address": f"{host}:{port}"}`                                                                                                        | n.a.                                                                                                                                                                        |
| Broadcast All Peers      | Todos os nós  | `{"type": "all_peers", "all_peers": self.all_peers}`                                                                                                        | n.a.                                                                                                                                                                        |
| Disconnect from a Node   | Qualquer nó   | `{"type": "disconnect", "address": f"{host}:{port}"}`                                                                                                       | n.a.                                                                                                                                                                        |
| Request Sudoku Solution  | Qualquer nó   | `{"type": "solve", "sudoku": self.sudoku, "row": i, "col": j, "address": self.id}`                                                                          | `{"type": "solution", "sudoku": self.resolving_sudoku, "col": self.resolving_peer[1], "row": self.resolving_peer[0], "solution": num_solution, "address": self.id}`         |
| Provide Sudoku Solution  | Qualquer nó   | `{"type": "solution", "sudoku": self.resolving_sudoku, "col": self.resolving_peer[1], "row": self.resolving_peer[0], "solution": num_solution, "address": self.id}` | n.a.                                                                                                                                                                        |
| Broadcast Stats          | Todos os nós  | `{"type": "stats", "origin": self.id, "solved": self.solver.solved_puzzles, "stats": {"address": self.id, "validations": self.solver.validations}, "all_stats": self.all_stats}` | n.a.                                                                                                                                                                        |
| Fetch Stats via HTTP     | Servidor HTTP | GET /stats                                                                                                                                                  | Aggregated Stats in JSON format                                                                                                                                             |
| Fetch Network Info via HTTP | Servidor HTTP | GET /network                                                                                                                                                | Network Info in JSON format                                                                                                                                                 |


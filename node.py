import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import threading
from urllib.parse import urlparse, parse_qs
from collections import deque
import logging
import time
import socket
import sys
import pickle
import os
from collections import deque
import time
import logging

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

class SudokuSolver:
    def __init__(self, base_delay = 0.01):
        logger.info("Initializing Sudoku solver")
        self.sudoku_board = None
        self.recent_requests = deque()
        self.solved_puzzles = 0
        self.validations = 0
        self.base_delay = base_delay
        print(base_delay)

    def solve_sudoku(self, sudoku):
        self.sudoku_board = sudoku
        logger.info(f"Solving Sudoku puzzle:\n{self.__str__(self.sudoku_board)}")
        if self.solve_sudoku_recursive(self.sudoku_board):
            self.solved_puzzles += 1
            logger.info(f"Sudoku puzzle solved:\n{self.__str__(self.sudoku_board)}")
            return self.sudoku_board
        else:
            logger.error("Failed to solve Sudoku puzzle")
            return None
            
    def is_valid_move(self, board, row, col, num):
        # Verifica se o número pode ser colocado na posição (row, col)
        if self.check(board):
            return True
        
        for i in range(9):
            if board[row][i] == num:
                return False
            if board[i][col] == num:
                return False

        # Verifica se o número pode ser colocado na sub-grade 3x3
        start_row, start_col = 3 * (row // 3), 3 * (col // 3)
        for i in range(3):
            for j in range(3):
                if board[start_row + i][start_col + j] == num:
                    return False

        return True

    def solve_sudoku_recursive(self, board): #Acabou por nao ser usada, mas é uma função recursiva que resolve o sudoku
        for row in range(9): # Loop pelas linhas
            for col in range(9): # Loop pelas colunas
                if board[row][col] == 0:    # Ve se a posição está vazia
                    for num in range(1, 10): # Loop pelos números de 1 a 9
                        print("row", row, "col", col, "num", num)
                        if self.is_valid_move(board, row, col, num): # Verifica se o número pode ser colocado na posição
                            board[row][col] = num # Coloca o número na posição
                            if self.solve_sudoku_recursive(board): # Chama a função recursivamente, se a solução for válida retorna True
                                return True
                            board[row][col] = 0 # Se a solução não for válida, coloca 0 na posição
                    return False
        return True
    
    def solve_sudoku_destributed(self, board, row, col):
        for num in range(1, 10):
            if self.is_valid_move(board, row, col, num):
                return num
        return None

    def check(self, board,interval=10, threshold=5):
        """Check if the given Sudoku solution is correct. """

        # alterei a função para receber o delay desde o init caso seja definido pelo utizador senão o delay é 0.01

        self.validations += 1 # aumenta o contador de validações sempre que é encontrada uma solução
        logger.info(f"Validation {self.validations} started")
        current_time = time.time()
        self.recent_requests.append(current_time)
        num_requests = len([t for t in self.recent_requests if current_time - t < interval])
        if num_requests > threshold:
            delay = self.base_delay * (num_requests - threshold + 1)  # Increase delay based on excess requests
            time.sleep(delay)
            logger.info(f"Delaying response by {delay:.2f}s")

        # Check rows
        for row in range(9):
            if sum(board[row]) != 45:
                logger.error(f"Row {row} is invalid")
                return False

        # Check columns
        for col in range(9):
            if sum([board[row][col] for row in range(9)]) != 45:
                logger.error(f"Column {col} is invalid")
                return False

        # Check 3x3 squares
        for i in range(3):
            for j in range(3):
                if sum([board[i*3+k][j*3+l] for k in range(3) for l in range(3)]) != 45:
                    logger.error(f"Square ({i}, {j}) is invalid")
                    return False

        return True
    
    def __str__(self, board):
        string_representation = "| - - - - - - - - - - - |\n"

        for i in range(9):
            string_representation += "| "
            for j in range(9):
                string_representation += str(board[i][j])
                string_representation += " | " if j % 3 == 2 else " "

            if i % 3 == 2:
                string_representation += "\n| - - - - - - - - - - - |"
            string_representation += "\n"

        return string_representation
   

class P2PNode:
    def __init__(self, host, port, anchor_node=None, handicap=0.001):
        self.solver = SudokuSolver(handicap)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
        self.id = f"{host}:{port}"
        self.host = host
        self.port = port

        self.anchor_node = anchor_node
        self.shutdown_flag = False
        self.solved = True
        self.flag = True

        self.sudoku = None
        self.initial_sudoku = None
        self.partial_solution = {}

        # Lista de peers
        self.total_peers = []
        self.peers_out = set() # peers a que este peer se conectou
        self.peers_in = set() # peers que se conectaram a este peer
        self.all_peers = {}
        self.peers_to_reconnect = {}

        self.handicap = handicap

        # Dicionário de peers ativos
        self.resolving_peer = None
        self.resolving_sudoku = None
        self.resolving_addr= None
        self.active_tasks = {}
        self.solution_queue = deque()
        self.task_queue = deque()
        self.tried_numbers_by_position = {} 
        self.stats_solved ={}
        self.all_stats = {
            "all": {
                "solved": 0,
                "validations": 0
            },
            "nodes": []
        }

    def send(self, address, msg):
        payload = json.dumps(msg).encode()
        self.sock.sendto(payload, address)

    def recv(self):
        try:
            payload, addr = self.sock.recvfrom(1024)
            if len(payload) == 0:
                return None, addr
            return payload, addr
        except socket.timeout:
            return None, None
        except Exception as e:
            logging.error(f"Error receiving data: {e}")
            return None, None

    def handle_message(self, msg):
        logging.info(f"Node {self.id} received message: {msg}")
        if msg["type"] == "connect":
            self.peers_out.add(msg["address"])
            self.peers_to_reconnect[msg["address"]] = True # Adiciona o peer à lista de peers a quem se deve reconectar, o value é True para mostrar que ainda nao morreu
            logging.info(f"Connected to peer at {msg['address']}")
            self.send((msg["address"].split(":")[0], int(msg["address"].split(":")[1])), {"type": "connected", "address": f"{self.host}:{self.port}"})

        elif msg["type"] == "connected":
            self.peers_in.add(msg["address"])
            self.peers_to_reconnect[msg["address"]] = True
            logging.info(f"Connected to peer at {msg['address']}")
            # adiciona o peer ao dicionario de peers, {peer ao qual estou conectado: este peer}
            self.all_peers[msg["address"]] = [self.id]
            
            all_peers_that_this_peer_is_connected_to = list(self.peers_out) + list(self.peers_in)
            for peer in all_peers_that_this_peer_is_connected_to:
                self.send((peer.split(":")[0], int(peer.split(":")[1])), {"type": "all_peers", "all_peers": self.all_peers})


        elif msg["type"] == "all_peers":
            all_peers_received = msg["all_peers"]
            logging.info("Received all peers information")
            
            self.broadcast_stats()

            # Itera sobre os pares de peers recebidos
            for peer_master, filhos in all_peers_received.items():
                if peer_master not in self.all_peers:
                    all_peers_copy = self.all_peers.copy()
                    self.all_peers[peer_master] = filhos
                    if all_peers_copy != self.all_peers:
                        self.broadcast_all_peers()
                else:
                    # Se o par de peers já existir, mescla as listas de filhos sem duplicatas
                    all_peers_copy = self.all_peers.copy()
                    self.all_peers[peer_master] = list(set(self.all_peers[peer_master] + filhos))
                    if all_peers_copy != self.all_peers:
                        self.broadcast_all_peers()

            # atualiza a lista de peers a quem se deve reconectar, no caso de la existir que esteja a False, ou seja, o peer morreu, mas é igual a algum ficlho ou pai
            for peer, filhos in self.all_peers.items():
                if peer in self.peers_to_reconnect and self.peers_to_reconnect[peer] == False:
                    self.peers_to_reconnect[peer] = True
                for filho in filhos:
                    if filho in self.peers_to_reconnect and self.peers_to_reconnect[filho] == False:
                        self.peers_to_reconnect[filho] = True


            # no caso deste peer so estar conecatdo a um peer, o peer pai, este peer vai tentar conectar-se a outro peer do sistema que esteja no all_peers e nao seja igual ao peer pai
            if (len(self.peers_in) == 1 or len(self.peers_out) == 1):
                # pode-se conectar a outro peer do sistema que nao seja igual ao peer pai, mas pode ser a um peer pai ou a um peer filho
                for peer, filhos in self.all_peers.items():
                    if peer not in self.peers_in and peer not in self.peers_out and peer != self.id:
                        host, port = peer.split(":")
                        self.send((host, int(port)), {"type": "connect", "address": f"{self.host}:{self.port}"})
                        break
            
            self.total_peers = list(self.all_peers.keys())
            for peers in self.all_peers.values():
                self.total_peers.extend(peers)

            # Remove duplicatas
            self.total_peers = list(set(self.total_peers))

            # Remove o próprio ID da lista, se estiver presente
            if self.id in self.total_peers:
                self.total_peers.remove(self.id)

            

        elif msg["type"] == "stats":
            logging.info(f"Received stats from {msg['origin']}: {msg['stats']}")
            address = msg["stats"]["address"]
            validations = msg["stats"]["validations"]
            solved = msg["solved"]
            received_all_stats = msg["all_stats"]

            # Atualiza as estatísticas globais com base nas estatísticas recebidas
            if received_all_stats["all"]["solved"] > self.all_stats["all"]["solved"]:
                self.all_stats["all"]["solved"] = received_all_stats["all"]["solved"]
            if received_all_stats["all"]["validations"] > self.all_stats["all"]["validations"]:
                self.all_stats["all"]["validations"] = received_all_stats["all"]["validations"]

            # Atualiza as estatísticas dos nós
            for received_node in received_all_stats["nodes"]:
                found = False
                for node in self.all_stats["nodes"]:
                    if node["address"] == received_node["address"]:
                        node["validations"] = max(node["validations"], received_node["validations"])
                        found = True
                        break
                if not found:
                    self.all_stats["nodes"].append(received_node)

            # Atualiza as estatísticas locais
            if address not in self.stats_solved and solved != 0:
                self.stats_solved[address] = solved
            elif address in self.stats_solved:
                if solved > self.stats_solved[address]:
                    self.stats_solved[address] = solved

            # Atualiza as estatísticas locais
            for node in self.all_stats["nodes"]:
                if node["address"] == address:
                    if node["validations"] < validations:
                        node["validations"] = validations
                    elif node["validations"] > validations:
                        validations = node["validations"]
                    break
            else:
                self.all_stats["nodes"].append({"address": address, "validations": validations})

            # Atualiza as estatísticas locais do próprio nó
            if self.id not in self.stats_solved and self.solver.solved_puzzles != 0:
                self.stats_solved[self.id] = self.solver.solved_puzzles
            elif self.id in self.stats_solved:
                if self.solver.solved_puzzles > self.stats_solved[self.id]:
                    self.stats_solved[self.id] = self.solver.solved_puzzles


            found = False
            for node in self.all_stats["nodes"]:
                if node["address"] == self.id:
                    if node["validations"] < self.solver.validations:
                        node["validations"] = self.solver.validations
                    if node["validations"] > self.solver.validations:
                        self.solver.validations = node["validations"]
                    found = True
                    break
            if not found:
                self.all_stats["nodes"].append({"address": self.id, "validations": self.solver.validations})

            # Atualiza as estatísticas globais
            self.all_stats["all"]["solved"] = sum(self.stats_solved.values())
            self.all_stats["all"]["validations"] = sum(node["validations"] for node in self.all_stats["nodes"])

            if self.resolving_peer != None:
                self.searching_solution()


        elif msg["type"] == "disconnect":
            if "row" in msg and "col" in msg:
                peer_resolving = (msg["row"], msg["col"])
                self.task_queue.appendleft(peer_resolving)
                
            if msg["address"] in self.peers_in:
                self.peers_in.remove(msg["address"])
            elif msg["address"] in self.peers_out:
                self.peers_out.remove(msg["address"])

            if msg["address"] in self.all_peers.keys() or any(msg["address"] in filhos for filhos in self.all_peers.values()):
                all_peers_copy = self.all_peers.copy()
                for peer, filhos in all_peers_copy.items():
                    if msg["address"] in filhos: 
                        filhos.remove(msg["address"])
                        self.all_peers[peer] = filhos
                        if self.all_peers[peer] == []:
                            del self.all_peers[peer]
                if msg["address"] in self.all_peers.keys():
                    del self.all_peers[msg["address"]]
                if all_peers_copy != self.all_peers and self.all_peers != {}:
                    self.broadcast_all_peers()

                self.peers_to_reconnect[msg["address"]] = False # O peer morreu

                # no caso do peer pai morrer de um node filho, o node filho vai tentar reconectar-se a outro node do sistema
                if msg["address"] in all_peers_copy.keys():
                    if self.id in all_peers_copy[msg["address"]]:
                        # se o peer pai morrer, o node filho vai tentar reconectar-se a outro node do sistema, primeiro pai do all_peers
                        if len(self.all_peers) != 0:
                            host, port = list(self.all_peers.keys())[0].split(":")
                            self.send((host, int(port)), {"type": "connect", "address": f"{self.host}:{self.port}"})
                        elif all_peers_copy[msg["address"]] != [] and len(all_peers_copy[msg["address"]]) != 1:
                            # se o peer pai morrer, o node filho vai tentar reconectar-se a outro node do sistema, primeiro filho do all_peers
                            for peer in all_peers_copy[msg["address"]]:
                                if peer != self.id:
                                    host, port = peer.split(":")
                                    self.send((host, int(port)), {"type": "connect", "address": f"{self.host}:{self.port}"})
                                    break

            logging.info(f"Disconnected from peer at {msg['address']}")
            if msg["address"] in self.total_peers:
                self.total_peers.remove(msg["address"])

            # da me print do tipo do msg("addrs") e das keys do active_tasks

            if msg["address"] in self.active_tasks:
                del self.active_tasks[msg["address"]]


        elif msg["type"] == "solve":
            logging.info(f"Received solve request from {msg['address']} for position {msg['row']}, {msg['col']}")
            self.resolving_addr = msg["address"]
            self.resolving_peer = (msg["row"], msg["col"])
            self.resolving_sudoku = msg["sudoku"]
            self.searching_solution()

        elif msg["type"] == "solution":
            num_solution = msg["solution"]
            row = msg["row"]
            col = msg["col"]
            sudoku = msg["sudoku"]
            peer = msg["address"]
            self.solution_queue.append((row, col, num_solution, peer))
            self.process_solutions()

    def searching_solution(self):
        num_solution = self.solver.solve_sudoku_destributed(self.resolving_sudoku, self.resolving_peer[0], self.resolving_peer[1])
        self.send((self.resolving_addr.split(":")[0], int(self.resolving_addr.split(":")[1])), {"type": "solution", "sudoku": self.resolving_sudoku, "col" : self.resolving_peer[1], "row": self.resolving_peer[0], "solution": num_solution, "address": self.id})
        self.resolving_peer = None
        self.resolving_sudoku = None
        self.resolving_addr = None
        self.broadcast_stats()

            
    def process_solutions(self):
        while self.solution_queue:
            self.flag = True
            row, col, num_solution, peer = self.solution_queue.popleft()
            logging.info(f"Processing solution {num_solution} from peer {peer} for position {row}, {col}")
            self.validate_solution(row, col, num_solution)
            if peer in self.active_tasks:
                del self.active_tasks[peer] 
        
            
    def fill_task_queue(self, sudoku):
        """Fill the task queue with empty positions of the Sudoku."""
        self.task_queue.clear()
        for i in range(9):
            for j in range(9):
                if sudoku[i][j] == 0:
                    self.task_queue.append((i, j))
            
    def solve_sudoku(self, sudoku):
        """Solve a Sudoku puzzle."""
        while True:
            self.process_solutions()
            self.solver.__str__(sudoku)
            
            while self.task_queue:
                if len(self.all_peers) != 0 and self.total_peers != []:
                    for peer in self.total_peers:
                        if peer not in self.active_tasks and self.task_queue:
                            logging.info(f"Assigning task to peer {peer} - resolve position {self.task_queue[0]}")
                            i, j = self.task_queue.popleft()
                            self.active_tasks[peer] = (i, j)
                            host, port = peer.split(":")
                            self.send((host, int(port)), {"type": "solve", "sudoku": self.sudoku, "row": i, "col": j, "address": self.id})
                            break
                else:
                    logging.info(f"No peers available to assign tasks, solving locally position {self.task_queue[0]}")
                    i, j = self.task_queue.popleft()
                    self.active_tasks[self.id] = (i, j)
                    num = self.solver.solve_sudoku_destributed(sudoku, i, j)
                    self.validate_solution(i, j, num)
                    self.process_solutions()

                
            
            if not self.flag and not self.task_queue and not self.solution_queue:
                break
            else:
                solved = []
                for i in range(9):
                    for j in range(9):
                        if self.sudoku[i][j] == 0:
                            solved.append((i, j))

                if len(solved) == 0 or len(solved) < 2:
                    self.flag = False
                    break
        if not self.task_queue:
                if self.solver.check(self.sudoku):
                    self.solved = True
                    self.solver.solved_puzzles += 1
                    logging.info(f"Sudoku puzzle solved:\n{self.solver.__str__(self.sudoku)}")
                    return self.sudoku
                else:
                    self.solved = True
                    self.solver.solved_puzzles += 1
                    logging.error("Failed to solve Sudoku puzzle")
                    return self.sudoku

    def validate_solution(self, row, col, num):
        """Validates the solution of a position on sudoku."""
        if num is not None:
            if self.solver.is_valid_move(self.sudoku, row, col, num):
                self.sudoku[row][col] = num
                self.partial_solution[(row, col)] = num
                return True
            else:
                self.task_queue.appendleft((row, col))

        else:
            # percorre primeiro a linha de todas no dic partial_solution e testa se algum dos numeros é valido no caso de ser usa esse numero, e coloca essa posiçao a 0 no self.sudoku
            # mas nao pode ser nenhum dos numeroos que vem no sudoku inicial
            self.flag = True
                                                    
            # Cria uma cópia da matriz do Sudoku para testar diferentes valores
            temp_board = [row[:] for row in self.sudoku]
                
            if (row, col) not in self.tried_numbers_by_position:
                   # o tried_numbers_by_position é um dicionario que guarda as posiçoes que ja foram testadas e os numeros que ja foram testados
                self.tried_numbers_by_position[(row, col)] = set()
                # Lista para armazenar os números válidos para a célula atual
            valid_numbers = {}
                # Verifica quais números no dicionário de solução parcial são válidos para a célula atual
            for c in range(9):
                if c != col and (row, c) in self.partial_solution:
                    temp_board[row][c] = 0  # Coloca 0 na posição atual para testar se o valor é válido
                    if self.solver.is_valid_move(temp_board, row, col, self.partial_solution[(row, c)]):
                        if self.partial_solution[(row, c)] != self.initial_sudoku[row][c] and (row, c, self.partial_solution[(row, c)]) not in self.tried_numbers_by_position[(row, col)]:
                            valid_numbers[(row, c)] = self.partial_solution[(row, c)]
                                        
                # Se houver números válidos, escolhemos um que não esteja presente na mesma linha, coluna ou subgrade
            for (r,c), value in valid_numbers.items():
                is_safe = True
                for i in range(9):
                    if temp_board[row][i] == value or temp_board[i][col] == value:
                        is_safe = False
                        break
                    if temp_board[3 * (row // 3) + i // 3][3 * (col // 3) + i % 3] == value:
                        is_safe = False
                        break
                if is_safe:
                    self.sudoku[row][col] = value
                    self.partial_solution[(row, col)] = value
                    # Apaga a solução parcial da posição anterior, pois a posição atual foi atualizada
                    del self.partial_solution[(r, c)]
                    self.tried_numbers_by_position[(row, col)].add((r, c, value))
                    self.sudoku[r][c] = 0
                    self.task_queue.appendleft((r, c))
                    return True
                                   
            # Se nenhum número válido for encontrado, coloca a posição a 0
            self.sudoku[row][col] = 0          
            self.flag = False
            # no caso da self.task_queue estar vazia, ou seja, nao haver mais posiçoes para resolver, o node vai tentar resolver a posiçao que nao conseguiu resolver
            return False
                
    def peer_sudoku_solve(self,sudoku):
        """Solve a Sudoku puzzle."""
        logging.info(f"Solving Sudoku puzzle:\n{self.solver.__str__(sudoku)}")
        self.solved = False
        self.flag = True
        self.initial_sudoku = [row[:] for row in sudoku]
        self.sudoku = [row[:] for row in sudoku]
        self.total_peers = list(self.all_peers.keys())
            
        self.total_peers = list(self.all_peers.keys())
        for peers in self.all_peers.values():
            self.total_peers.extend(peers)

        self.total_peers = list(set(self.total_peers))

        if self.id in self.total_peers:
            self.total_peers.remove(self.id)       

        self.fill_task_queue(self.sudoku)
        self.solve_sudoku(self.sudoku)
        while self.solved == False:
            pass
        self.broadcast_stats()
        return self.sudoku

    def connect_to_anchor_node(self):
        """Conecta-se ao anchor node."""
        logging.info(f"Connecting to anchor node {self.anchor_node}")
        host, port = self.anchor_node.split(":")
        msg = {"type": "connect", "address": f"{self.host}:{self.port}"}  
        self.send((host, int(port)), msg)
        payload, _ = self.recv()
        if payload is not None:
            msg = json.loads(payload.decode())
            self.handle_message(msg)

    def broadcast_all_peers(self):
        """Envia a lista de pares de peers atualizada para todos os peers conectados."""
        logging.info("Sending all peers information to all peers")
        all_peers_message = {"type": "all_peers", "all_peers": self.all_peers}
        all_peers_that_this_peer_is_connected_to = list(self.peers_out) + list(self.peers_in)
        for peer in all_peers_that_this_peer_is_connected_to:
            host, port = peer.split(":")
            self.send((host, int(port)), all_peers_message)
        

    def broadcast_stats(self):
        """Envia as estatísticas atuais para todos os peers conectados."""
        logging.info("Sending stats to all peers")
        stats_msg = {
            "type": "stats",
            "origin": self.id,
            "solved": self.solver.solved_puzzles,
            "stats": {
                "address": self.id,
                "validations": self.solver.validations,
            }, 
            "all_stats": self.all_stats,
        }
        all_peers_that_this_peer_is_connected_to = list(self.peers_out) + list(self.peers_in)
        for peer in all_peers_that_this_peer_is_connected_to:
            host, port = peer.split(":")
            self.send((host, int(port)), stats_msg)
            
    def get_stats(self):
        """Retorna as estatísticas atuais do node."""
        if self.id not in self.stats_solved and self.solver.solved_puzzles != 0:
            self.stats_solved[self.id] = self.solver.solved_puzzles
        elif self.id in self.stats_solved:
            if self.solver.solved_puzzles > self.stats_solved[self.id]:
                self.stats_solved[self.id] = self.solver.solved_puzzles

        found = False
        for node in self.all_stats["nodes"]:
            if node["address"] == self.id:
                if node["validations"] < self.solver.validations:
                    node["validations"] = self.solver.validations
                found = True
                break
        if not found:
            self.all_stats["nodes"].append({"address": self.id, "validations": self.solver.validations})

        # Atualiza as estatísticas globais
        self.all_stats["all"]["solved"] = sum(self.stats_solved.values())
        self.all_stats["all"]["validations"] = sum(node["validations"] for node in self.all_stats["nodes"])

        return self.all_stats
  
    
    def run(self):
        """Run the P2P server."""
        self.sock.bind((self.host, self.port))
        logging.info(f"P2P Server with id {self.id} listening on {self.host}:{self.port}")
        if self.anchor_node:
            self.connect_to_anchor_node()
        while not self.shutdown_flag:
            try:
                logger.info("Peers that this node is connected to " + str(self.peers_in))
                logger.info("Peers that are connected to this node: " + str(self.peers_out))
                logger.info("All peers: " + str(self.all_peers))
                logger.info("Peers to reconnect: " + str(self.peers_to_reconnect) + "\n")
                payload, _ = self.recv()
                if payload is not None:
                    msg = json.loads(payload.decode())
                    self.handle_message(msg)
            except KeyboardInterrupt:
                self.shutdown()

            except Exception as e:
                logging.error(f"Error receiving data: {e}")
                continue
                
    def shutdown(self):
        self.broadcast_stats()
        self.shutdown_flag = True
        peer_list = list(self.peers_out) + list(self.peers_in)
        for peer in peer_list:
            if self.resolving_peer == None:
                msg = {"type": "disconnect", "address": self.id}
            else:
                msg = {"type": "disconnect", "address": self.id, "row": self.resolving_peer[0], "col": self.resolving_peer[1]}
            host, port = peer.split(":")
            self.send((host, int(port)), msg)
            logging.info(f"Sent disconnect message to {peer}")
        logging.info(f"Shutting down P2P node id {self.id}")
          

class SudokuHTTPServer(BaseHTTPRequestHandler):
    def __init__(self, p2p_node, *args, **kwargs):
        self.p2p_node = p2p_node
        super().__init__(*args, **kwargs)

    def _send_response(self, content, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(content).encode())

    def do_POST(self):
        if self.path == "/solve":
            initial_time = time.time()
            logging.info("Received /solve POST request")
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            sudoku = json.loads(post_data.decode('utf-8'))['sudoku']
            solution = self.p2p_node.peer_sudoku_solve(sudoku)

            final_time = time.time()
            execution_time = final_time - initial_time
            logging.info(f"Execution time: {execution_time}")

            if solution:
                self._send_response(solution)
            else:
                self._send_response({"error": "No solution found", "solution" : solution}, 400)
        else:
            self._send_response({"error": "Invalid endpoint"}, 404)

    def do_GET(self):
        if self.path == "/stats":
            logging.info("Received /stats GET request")
            self._send_response(self.p2p_node.get_stats())
        elif self.path == "/network":
            logging.info("Received /network GET request")
            if self.p2p_node.all_peers != {}:
                self._send_response(self.p2p_node.all_peers)
            else:
                dic = {self.p2p_node.id: []}
                self._send_response(dic)
        else:
            self._send_response({"error": "Invalid endpoint"}, 404)


def run_http_server(p2p_node, http_port):
    host = "192.168.1.126"
    server_address = (host, http_port)
    httpd = HTTPServer(server_address, lambda *args, **kwargs: SudokuHTTPServer(p2p_node, *args, **kwargs))
    logging.info(f"Starting HTTP server on {host}:{http_port}")
    
    httpd.serve_forever()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sudoku Solver Node", conflict_handler='resolve')
    parser.add_argument('-p', type=int, default=8001, help='HTTP port')
    parser.add_argument('-s', type=int, default=7000, help='P2P port')
    parser.add_argument('-a', help='Anchor node address (host:port)')
    parser.add_argument('-h', type=float, default=1, help='Handicap (delay in ms) for validation')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    
    p2p_node = P2PNode("192.168.1.126", args.s, anchor_node=args.a, handicap=args.h/100)
    http_thread = threading.Thread(target=run_http_server, args=(p2p_node, args.p))
    http_thread.daemon = True
    http_thread.start()
    p2p_node.run()

    
"""Michal Bochnak, hw3, CS 450, UIC"""
#
# hw3.py
#
# Michal Bochnak
# CS 450
# March 7, 2018
#
# Program to create server, or clients to play a war card game.
# Server can handle multiple clients (i.e 1000) and host war game for them,
# using async I/O.
# Server pairs two clents together for each session.
# Each client automatically sends the cards to the server.
#


import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
import sys


# Namedtuples work like classes, but are much more lightweight so they end
# up being faster. It would be a good idea to keep objects in each of these
# for each game which contain the game's state, for instance things like the
# socket, the cards given, the cards still available, etc.
Game = namedtuple('Game', 'p1 p2')


class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3


class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2


def compare_cards(card1, card2):
    """
    Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """
    if card1 % 13 > card2 % 13:
        return 1
    elif card1 % 13 == card2 % 13:
        return 0
    return -1


def get_shuffled_card_deck():
    """
    Shuffle and return shuffled deck of cards
    """
    deck = list(range(0, 52))
    random.shuffle(deck)
    return deck


async def process_game(game_session):
    """
    Handles all actions required to process a game. Game consists of
    2 clients served simultaneously
    """
    try:
        # get readers and writers for both clients
        p1_reader = game_session.p1[0]
        p1_writer = game_session.p1[1]
        p2_reader = game_session.p2[0]
        p2_writer = game_session.p2[1]

        # wait till ready to play
        p1_answer = int.from_bytes(await p1_reader.readexactly(2),
                                   byteorder='big')
        p2_answer = int.from_bytes(await p2_reader.readexactly(2),
                                   byteorder='big')

        # dealt the cards if response was WANTGAME from both clients
        if p1_answer == Command.WANTGAME.value and p2_answer \
                == Command.WANTGAME.value:
            deck = get_shuffled_card_deck()
            # hand halves to each player
            p1_cards = deck[:26]
            p2_cards = deck[26:]
            p1_writer.write(bytes(Command.GAMESTART.value) + bytes(p1_cards))
            p2_writer.write(bytes(Command.GAMESTART.value) + bytes(p2_cards))

            # process game
            for _ in range(0, 26):
                p1_answer = await p1_reader.readexactly(2)
                p2_answer = await p2_reader.readexactly(2)

                # make sure correct command received from both players
                if int.from_bytes(p1_answer[:1], byteorder='little') \
                        == Command.PLAYCARD.value \
                        and int.from_bytes(p2_answer[:1], byteorder='little') \
                        == Command.PLAYCARD.value:
                    p1_card = int.from_bytes(p1_answer[1:], byteorder='little')
                    p2_card = int.from_bytes(p2_answer[1:], byteorder='little')
                    # verify that used card is correct
                    if not (p1_card in p1_cards and p2_card in p2_cards):
                        break
                    p1_cards.remove(p1_card)
                    p2_cards.remove(p2_card)
                    result = compare_cards(p1_card, p2_card)
                    # p1 won
                    if result == 1:
                        p1_writer.write(bytes([Command.PLAYRESULT.value,
                                               Result.WIN.value]))
                        p2_writer.write(bytes([Command.PLAYRESULT.value,
                                               Result.LOSE.value]))
                    # p2 won
                    elif result == 0:
                        p1_writer.write(bytes([Command.PLAYRESULT.value,
                                               Result.DRAW.value]))
                        p2_writer.write(bytes([Command.PLAYRESULT.value,
                                               Result.DRAW.value]))
                    # draw
                    else:
                        p1_writer.write(bytes([Command.PLAYRESULT.value,
                                               Result.LOSE.value]))
                        p2_writer.write(bytes([Command.PLAYRESULT.value,
                                               Result.WIN.value]))
                    # else:
                    #     break
                else:
                    break

        p1_writer.close()
        p2_writer.close()

    except BaseException:
        p1_writer.close()
        p2_writer.close()



def accept_client(reader, writer):
    """
    Every 2 clients accepted run new game co-routine
    """
    if accept_client.GAME.p1 is None:
        accept_client.GAME = Game(p1=(reader, writer), p2=None)
    else:
        accept_client.GAME = Game(accept_client.GAME.p1, p2=(reader, writer))
        asyncio.Task(process_game(accept_client.GAME))
        accept_client.GAME = Game(p1=None, p2=None)


accept_client.GAME = Game(p1=None, p2=None)


def serve_game(host, port):
    """
    Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.start_server(accept_client,
                                                 host=host, port=port))
    loop.run_forever()


async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    """
    async with sem:
        return await client(host, port, loop)


async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port, loop=loop)
        # send want game
        writer.write(b"\0\0")
        card_msg = await reader.readexactly(27)
        myscore = 0
        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1
        if myscore > 0:
            result = "Won"
        elif myscore < 0:
            result = "Lost"
        else:
            result = "Drew"
        logging.debug("Game complete, I %s", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.streams.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0


def main(args):
    """
    launch a client/server
    """
    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return
    else:
        loop = asyncio.get_event_loop()

    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        sem = asyncio.Semaphore(1000)
        num_clients = int(args[3])
        clients = [limit_client(host, port, loop, sem)
                   for x in range(num_clients)]
        async def run_all_clients():
            """
            use `as_completed` to spawn all clients simultaneously
            and collect their results in arbitrary order.
            """
            completed_clients = 0
            for client_result in asyncio.as_completed(clients):
                completed_clients += await client_result
            return completed_clients
        res = loop.run_until_complete(
            asyncio.Task(run_all_clients(), loop=loop))
        logging.info("%d completed clients", res)

    loop.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])

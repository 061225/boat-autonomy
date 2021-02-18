from boat_simulation.hardware_tests.radio_test import Robot
from multiprocessing import Process, Pipe
from boat_simulation.hardware_tests.radio_simulator import RadioSim

from time import sleep, time


SEND_MSG_INTERVAL = 0.5


def base_station_run(radio_conn):
    last_published = None

    while True:
        if last_published is None or time() - last_published >= SEND_MSG_INTERVAL:
            msg = bytes(" ".join(["Hello, can you hear me?" for i in range(1)]), "utf-8")
            msg += b'\4'
            packets = [msg[252*i: min(len(msg), 252*i + 252)] for i in range(1 + (len(msg) // 252))]
            for p in packets:
                if p != b'':
                    radio_conn.send(p)
            last_published = time()
        if radio_conn.poll():
            received_packet = radio_conn.recv()

            for k in range(2, len(received_packet)):
                if received_packet[k] == 0:
                    break

            received_data = received_packet[2: k]
            print(f"Received robot status: {received_data}")


def robot_run(radio):
    robot = Robot(radio=radio)
    robot.run()


def main():
    base_station_conn, radio_conn = Pipe()
    radio = RadioSim(base_station_conn)

    robot_proc = Process(target=robot_run, args=(radio,))

    try:
        robot_proc.start()
        base_station_run(radio_conn)
    finally:
        robot_proc.terminate()


if __name__ == '__main__':
    main()

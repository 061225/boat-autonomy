from boat_simulation.simple import SimpleBoatSim, Action
from boat_simulation.latlon import LatLon

from controller.keyboard_controller import KeyboardController
from controller.autonomy_controller_template import AutonomyControllerTemplate
from controller.complementary_filter import ComplementaryFilterController
from controller.minimal_controller import MinimalController
from controller.scipy_opt_controller import ScipyOptController
from controller.scipy_logging_controller import ScipyLoggingController
from controller.pid_controller import PIDController
from controller.slsqp_controller import SLSQPController
from controller.planning_controller import PlanningController
from controller.control_planner import ControlPlanner

from multiprocessing import Process, Pipe

import argparse
import pygame
import types
import json
import time


def parse_args():
    controller_arg_names = ["keyboard", "autonomy_template", "complementary_filter_test", "minimal_controller", "scipy_logging", "scipy_opt", "pid", "slsqp", "planning", "c_planning"]
    state_modes = ["ground_truth", "noisy", "sensor"]

    parser = argparse.ArgumentParser(description='Run the boat simulation.')
    parser.add_argument('--controller', '-c', help="Choose the name of the controller to use",
                        choices=controller_arg_names, default=controller_arg_names[0])
    parser.add_argument('--current_level', '-cl', help="Choose the intensity of currents in the simulation in cm/s",
                        default=50)
    parser.add_argument('--max_obstacles', '-mo', help="Choose the maximum number of obstacles on screen at any time",
                        default=10)
    parser.add_argument('--state_mode', '-sm', help="Choose the representation of the simulation state available to the boat",
                        choices=state_modes, default=state_modes[0])
    parser.add_argument('--no_render', '-nr', help="Set this flag to true to disable rendering the simulation",
                        action="store_true", default=False)
    parser.add_argument('--no_drag', '-nd', help="Set this flag to true to disable drag forces",
                        action="store_true", default=False)
    args = parser.parse_args()
    return args


def format_state(state, env):
    boat_x, boat_y, boat_speed, boat_angle, boat_ang_vel, obstacles = state
    currents = env.compute_ocean_current(LatLon(boat_y, boat_x))
    out_dict = {
        "state": {
            "lat": boat_y,
            "lon": boat_x,
            "speed": boat_speed,
            "angle": boat_angle,
            "ang_vel": boat_ang_vel,
            "ocean_current_x": currents[0],
            "ocean_current_y": currents[1],
            "desired_speed": env.speed,
            "obstacles": obstacles
        }
    }
    return json.dumps(out_dict)


def simulation(args, controller_conn):
    """
    Simulates movements of the boat.

    This function is to be executed in the process simulates the boat. It creates
    an instance of the SimpleBoatSim class, repeatedly publishes state
    information and receives actions taken by the boat.
    """
    env = SimpleBoatSim(current_level=int(args.current_level), state_mode=args.state_mode, max_obstacles=int(args.max_obstacles), apply_drag_forces=(not bool(args.no_drag)))
    state = env.reset()

    env.set_waypoints(controller_conn.recv())
    controller_conn.send(format_state(state, env))

    while True:
        events = pygame.event.get()

        to_send = False
        if controller_conn.poll():
            action = controller_conn.recv()
            to_send = True
        else:
            action = Action(0, 0)

        state, _, end_sim, _ = env.step(action)

        if to_send:
            controller_conn.send(format_state(state, env))

        if not args.no_render:
            env.render()

        if end_sim:
            # This can be replaced with env.close() to end the simulation.
            state = env.reset()


def controller(args, simulation_conn, radio_conn):
    """
    Specifies linear and angular accelerations to be applied by boat.

    This function is to be executed in the process that handles (or simulates
    handling) the main control of the boat.
    """
    controller = None
    if args.controller == "keyboard":
        controller = KeyboardController(in_sim=False)
    elif args.controller == "autonomy_template":
        controller = AutonomyControllerTemplate(in_sim=False)
    elif args.controller == "complementary_filter_test":
        controller = ComplementaryFilterController(in_sim=False)
    elif args.controller == "minimal_controller":
        controller = MinimalController(in_sim=False)
    elif args.controller == "scipy_logging":
        controller = ScipyLoggingController(in_sim=False)
    elif args.controller == "scipy_opt":
        controller = ScipyOptController(in_sim=False)
    elif args.controller == "slsqp":
        controller = SLSQPController(in_sim=False)
    elif args.controller == "pid":
        controller = PIDController(in_sim=False)
    elif args.controller == "planning":
        controller = PlanningController(in_sim=False)
    elif args.controller == "c_planning":
        controller = ControlPlanner(in_sim=False)

    waypoints = radio_conn.recv()
    simulation_conn.send(waypoints)
    env = types.SimpleNamespace(waypoints=waypoints)

    while True:
        if simulation_conn.poll():
            state = json.loads(simulation_conn.recv())["state"]
            state = state["lon"], state["lat"], state["speed"], state["desired_speed"], state["angle"], state["ang_vel"], state["ocean_current_x"], state["ocean_current_y"], state["obstacles"]

            action = controller.choose_action(env, state)
            simulation_conn.send(action)


def radio(args, controller_conn):
    """
    Sends waypoint information to the controller program.

    This function is to be executed in the process that processes (or simulates
    processing) radio input from the dashboard to the controller that specifies
    where the robot is supposed to go.
    """
    env = SimpleBoatSim(current_level=int(args.current_level), state_mode=args.state_mode, max_obstacles=int(args.max_obstacles))
    state = env.reset()

    controller_conn.send(env.waypoints)


def main():
    args = parse_args()

    controller_sim_1, controller_sim_2 = Pipe()
    controller_radio_1, controller_radio_2 = Pipe()

    radio_proc = Process(target=radio, args=(args, controller_radio_1))
    controller_proc = Process(target=controller, args=(args, controller_sim_2, controller_radio_2))

    try:
        radio_proc.start()
        controller_proc.start()
        simulation(args, controller_sim_1)

    finally:
        controller_proc.terminate()
        radio_proc.terminate()


if __name__ == '__main__':
    main()

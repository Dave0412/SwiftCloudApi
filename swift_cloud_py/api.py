from typing import Tuple

import requests
from requests import Response

from authentication.authentication import authenticate
from authentication.authentication_errors import UnkownCloudException, UnauthorizedException, BadRequestException
from authentication.check_internet_connection import ensure_has_internet
from entities.control_output.fixed_time_schedule import FixedTimeSchedule
from entities.control_output.phase_diagram import PhaseDiagram
from entities.intersection.intersection import Intersection
from entities.scenario.arrival_rates import ArrivalRates
from enums import ObjectiveEnum

CLOUD_API_URL = "https://desktop-test-api.swiftmobility.eu" # TODO: change


def check_status_code(response: Response) -> None:
    """
    check status code returned by rest-api call; raises appropriate error if status code indicates that the call was
    not succesfull.
    """
    if response.status_code in [400]:
        raise BadRequestException(str(response.json()))
    elif response.status_code in [401]:
        raise UnauthorizedException("JWT validation failed: Missing or invalid credentials")
    elif response.status_code in [402]:
        raise UnauthorizedException("Insufficient credits (cpu seconds) left.")
    elif response.status_code in [403]:
        raise UnauthorizedException("Forbidden.")
    elif response.status_code in [426]:
        raise UnauthorizedException(f"The cloud api is still in the beta phase; this means it might change. "
                                    f"Message from cloud: {response.json()['msg']}.")
    elif response.status_code in [504]:
        raise TimeoutError
    elif response.status_code != 200:
        raise UnkownCloudException


class SwiftMobilityCloudApi:
    """
    Class to communicate with the cloud-api of swift mobility (and automating authentication).
    Using this class simplifies the communication with the cloud-api (compared to using the rest-api's directly)
    """
    _authentication_token: str = None  # this token is updated by the @authenticate decorator

    @classmethod
    @ensure_has_internet
    @authenticate
    def get_optimized_fts(cls, intersection: Intersection, arrival_rates: ArrivalRates,
                          min_period_duration: float = 0.0, max_period_duration: float = 180,
                          objective: ObjectiveEnum = ObjectiveEnum.min_delay
                          ) -> Tuple[FixedTimeSchedule, PhaseDiagram, float]:
        """
        Optimize a fixed-time schedule
        :param intersection: intersection for which to optimize the fts (contains signalgroups, conflicts and more)
        :param arrival_rates: arrival rates in personal car equivalent per hour (PCE/h)
        :param min_period_duration: minimum period duration of the fixed-time schedule in seconds
        :param max_period_duration: minimum period duration of the fixed-time schedule in seconds
        :param objective: what kpi (key performance indicator) to optimize. The following options are available:
         - ObjectiveEnum.min_delay: minimize the delay experienced by road users at the intersection
         - ObjectiveEnum.min_period: search for the fixed-time schedule with the smallest period duration for which
         all traffic lights are 'stable' (the greenyellow interval is large enough to prevent queue lengths from
         increasing indefinitely)
         - ObjectiveEnum.max_capacity: search for the fixed-time schedule that can handle the largest (percentual)
         increase in traffic.
        :return: fixed-time schedule, associated phase diagram and the objective value
        (minimized delay, minimized period, or maximum percentual increase in traffic divided by 100, e.g. 1 means
        currently at the verge of stability)
        """
        # TODO: introduce horizon parameter and QueueLength parameter and update doc-string
        for signalgroup in intersection.signalgroups:
            assert signalgroup.id in arrival_rates.id_to_arrival_rates, \
                f"arrival rate(s) must be specified for signalgroup {signalgroup.id}"
            assert len(arrival_rates.id_to_arrival_rates[signalgroup.id]) == len(signalgroup.traffic_lights), \
                f"arrival rate(s) must be specified for all traffic lights of signalgroup {signalgroup.id}"

        # TEMP TODO: remove
        request_id = "123-456"
        version = "0.7.0.alpha"

        endpoint = f"{CLOUD_API_URL}/fts-optimization"
        headers = {'authorization': 'Bearer {0:s}'.format(cls._authentication_token)}

        # rest-api call
        try:
            json_dict = dict(
                intersection=intersection.to_json(),
                arrival_rates=arrival_rates.to_json(),
                min_period_duration=min_period_duration,
                max_period_duration=max_period_duration,
                objective=objective.value,
                version=version,  # TODO: remove
                request_id=request_id  # TODO: remove
            )
            r = requests.post(endpoint, json=json_dict, headers=headers)
        except requests.exceptions.ConnectionError:
            raise UnkownCloudException("Connection with swift mobility cloud api could not be established")

        # check for errors
        check_status_code(response=r)

        # parse output
        output = r.json()
        objective_value = output["obj_value"]
        fixed_time_schedule = FixedTimeSchedule.from_json(output["fixed_time_schedule"])
        phase_diagram = PhaseDiagram.from_json(output["phase_diagram"])

        return fixed_time_schedule, phase_diagram, objective_value

    @classmethod
    @ensure_has_internet
    @authenticate
    def get_phase_diagram(cls, intersection: Intersection, fixed_time_schedule: FixedTimeSchedule) -> PhaseDiagram:
        """
        Get the phase diagram specifying the order in which the signal groups have their greenyellow intervals
        in the fixed-time schedule
        :param intersection: intersection for which to optimize the fts (contains signalgroups, conflicts and more)
        :param fixed_time_schedule: fixed-time schedule for which we want to retrieve the phase diagram.
        :return:
        """
        endpoint = f"{CLOUD_API_URL}/phase-diagram-computation"
        headers = {'authorization': 'Bearer {0:s}'.format(cls._authentication_token)}

        # rest-api call
        try:
            json_dict = dict(
                intersection=intersection.to_json(),
                greenyellow_intervals=fixed_time_schedule.to_json()["greenyellow_intervals"],
                period=fixed_time_schedule.to_json()["period"]
            )
            r = requests.post(endpoint, json=json_dict, headers=headers)
        except requests.exceptions.ConnectionError:
            raise UnkownCloudException("Connection with swift mobility cloud api could not be established")

        # check for errors
        check_status_code(response=r)
        output = r.json()

        # parse output
        phase_diagram = PhaseDiagram.from_json(output["phase_diagram"])
        return phase_diagram


if __name__ == "__main__":
    from examples.load_from_smd_export import run_load_from_smd_example
    run_load_from_smd_example()

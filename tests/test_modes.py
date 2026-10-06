import unittest

from simurg.modes.flight_modes import (Context, ContingencyManager,
                                       FlightModeMachine, Mode)


def fly_to_mission(fsm, ctx):
    ctx.preflight_ok = True
    assert fsm.request(Mode.ARMED, ctx)
    assert fsm.request(Mode.VTOL_TAKEOFF, ctx)
    ctx.landed, ctx.alt_agl_m = False, 50
    assert fsm.request(Mode.TRANSITION_FW, ctx)
    ctx.airspeed_mps = 24
    assert fsm.request(Mode.CRUISE, ctx)
    assert fsm.request(Mode.MISSION, ctx)


class ModeTest(unittest.TestCase):
    def test_cannot_arm_without_preflight(self):
        fsm = FlightModeMachine()
        self.assertFalse(fsm.request(Mode.ARMED, Context()))

    def test_cannot_transition_to_cruise_below_speed(self):
        fsm, ctx = FlightModeMachine(), Context(preflight_ok=True)
        fsm.request(Mode.ARMED, ctx)
        fsm.request(Mode.VTOL_TAKEOFF, ctx)
        ctx.alt_agl_m = 50
        fsm.request(Mode.TRANSITION_FW, ctx)
        ctx.airspeed_mps = 15
        self.assertFalse(fsm.request(Mode.CRUISE, ctx))

    def test_full_nominal_cycle(self):
        fsm, ctx = FlightModeMachine(), Context()
        fly_to_mission(fsm, ctx)
        self.assertTrue(fsm.request(Mode.RETURN, ctx))
        self.assertTrue(fsm.request(Mode.TRANSITION_VTOL, ctx))
        ctx.airspeed_mps = 3
        self.assertTrue(fsm.request(Mode.VTOL_LAND, ctx))
        ctx.landed = True
        self.assertTrue(fsm.request(Mode.DISARMED, ctx))

    def test_contingency_priorities(self):
        cm = ContingencyManager()
        fsm, ctx = FlightModeMachine(), Context()
        fly_to_mission(fsm, ctx)
        ctx.link_lost_s = 45
        self.assertIs(cm.evaluate(fsm, ctx), Mode.RETURN)

        fsm, ctx = FlightModeMachine(), Context()
        fly_to_mission(fsm, ctx)
        ctx.link_lost_s, ctx.nav_integrity_ok = 45, False
        self.assertIs(cm.evaluate(fsm, ctx), Mode.LOITER_HOLD)   # nav > link

        fsm, ctx = FlightModeMachine(), Context()
        fly_to_mission(fsm, ctx)
        ctx.nav_integrity_ok, ctx.hover_feasible = False, False
        self.assertIs(cm.evaluate(fsm, ctx), Mode.EMERGENCY_LAND)

        ctx.controllable = False
        self.assertIs(cm.evaluate(fsm, ctx), Mode.PARACHUTE)
        self.assertIsNone(cm.evaluate(fsm, ctx))


if __name__ == "__main__":
    unittest.main()

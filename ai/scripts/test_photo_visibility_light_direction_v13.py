import unittest
import numpy as np
from test_photo_visibility_joint_local_v12 import JointWitnessTests as _Base
import photo_visibility_light_direction_v13 as v13
import photo_visibility_local_direction_v12 as v12


class LightDirectionTests(_Base):
    module=v13

    def test_direction_invariant_to_affine_lighting_on_actual_run(self):
        y,x=np.indices((64,64),dtype=float)
        ridge=100+2*np.cos(2*np.pi*x/8)
        lit=ridge+2*y
        base=v13.local_direction(ridge,0.,[8,40])
        corrected=v13.local_direction(lit,0.,[8,40])
        self.assertLess(v12.local_direction(lit,0.,[8,40])['local_direction_alignment'],.7)
        self.assertAlmostEqual(base['local_direction_alignment'],corrected['local_direction_alignment'],places=12)
        self.assertGreater(corrected['local_direction_alignment'],.99)
        self.assertAlmostEqual(corrected['removed_gradient_xy'][1],2.,places=10)


# Do not rediscover the imported base TestCase as another experiment.
del _Base
if __name__=='__main__':unittest.main()

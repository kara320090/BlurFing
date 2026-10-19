import unittest
import numpy as np
from photo_visibility_local_audit_v1 import local_audit
from photo_visibility_gate_audit_v1 import audit_ridge_level


class LocalAuditTests(unittest.TestCase):
    def test_native_plane_decision_reproduced_and_box_does_not_change_observation(self):
        y,x=np.indices((160,192));g=np.clip(90+.2*x+7*np.sin(2*np.pi*x/8),0,255).astype(np.uint8);m=np.ones(g.shape,bool)
        a=local_audit(g,m,[32,32,96,96]);b=local_audit(g,m)
        self.assertEqual(a['all'],b['all'])
        self.assertEqual(a['all']['accepted'],audit_ridge_level(g,m,512)['planar_detrended_credible_windows'])
        self.assertGreater(a['human_evidence']['windows'],0)
        self.assertEqual(a['human_evidence']['accepted'],0)
        self.assertGreater(a['human_evidence']['one_gate_removed']['contrast'],0)

    def test_no_evidence_windows_not_negative_and_invalid_coordinates_rejected(self):
        g=np.full((80,80),128,np.uint8);m=np.ones(g.shape,bool)
        r=local_audit(g,m,[10,10,22,22]);self.assertEqual(r['human_evidence']['windows'],0)
        self.assertFalse(r['used_by_protection'])
        for box in ([0,0,90,90],[0.,0,32,32],[0,0,0,2]):
            with self.assertRaises(ValueError):local_audit(g,m,box)
        m[0,0]=False
        with self.assertRaises(ValueError):local_audit(g,m,[0,0,32,32])


if __name__=='__main__':unittest.main()

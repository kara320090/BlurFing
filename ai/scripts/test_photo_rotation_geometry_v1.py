import unittest
import numpy as np
from photo_pixel_cell_support_v1 import resize_support
from photo_rotation_orbit_v1 import combine_restored_probabilities,predict_orbit


class PixelCellSupportTests(unittest.TestCase):
    def test_all_positive_overlap_cells_and_exact_edge_contacts(self):
        mask=np.array([[True,False,False]],bool)
        np.testing.assert_array_equal(resize_support(mask,(1,2)),[[True,False]])
        np.testing.assert_array_equal(resize_support(mask,(1,6)),[[True,True,False,False,False,False]])
        np.testing.assert_array_equal(resize_support(np.ones((2,4),bool),(1,1)),[[True]])

    def test_rectangular_rotations_reflections_with_tie_sizes(self):
        rng=np.random.default_rng(91)
        for h,w in [(2,4),(3,8),(17,29),(29,17)]:
            mask=rng.random((h,w))>.6
            for H,W in [(1,1),(2,3),(4,2),(8,11),(31,47)]:
                expected=resize_support(mask,(H,W))
                for k in range(4):
                    shape=(W,H) if k%2 else (H,W)
                    got=resize_support(np.rot90(mask,k).copy(),shape)
                    np.testing.assert_array_equal(got,np.rot90(expected,k))
                np.testing.assert_array_equal(resize_support(mask[:,::-1].copy(),(H,W)),expected[:,::-1])

    def test_roundtrip_never_loses_original_true_cells_but_is_not_new_permission(self):
        rng=np.random.default_rng(3);mask=rng.random((39,71))>.85;before=mask.copy()
        for shape in [(1,1),(3,5),(17,31),(52,90)]:
            result=resize_support(resize_support(mask,shape),list(mask.shape))
            self.assertFalse(np.any(mask&~result))
        np.testing.assert_array_equal(mask,before)

    def test_contracts_empty_shapes_bool_dimensions_and_dtypes(self):
        for mask,shape in [(np.zeros((0,2),bool),(1,1)),(np.zeros((2,2),np.uint8),(1,1)),
                           (np.zeros((2,2),bool),(True,2)),(np.zeros((2,2),bool),(0,2))]:
            with self.assertRaises(ValueError):resize_support(mask,shape)


class OrbitTests(unittest.TestCase):
    def fixture(self):
        rng=np.random.default_rng(81);rgb=rng.integers(0,256,(17,29,3),np.uint8)
        body=np.ones((17,29),bool);tip=np.zeros_like(body);tip[:3,5:8]=True
        return rgb,body,tip

    @staticmethod
    def orientation_sensitive(rgb,body,tip):
        y,x=np.indices(body.shape)
        return np.clip(rgb[:,:,0].astype(np.float32)/300+(x%5).astype(np.float32)*.02+tip*.01,0,1).astype(np.float32)

    def test_complete_view_ensemble_is_quarter_turn_equivariant_including_tiles(self):
        arrays=self.fixture();result,report=predict_orbit(*arrays,self.orientation_sensitive)
        for k in range(1,4):
            moved=[np.rot90(a,k).copy() for a in arrays]
            probability,_=predict_orbit(*moved,self.orientation_sensitive)
            np.testing.assert_array_equal(probability,np.rot90(result,k))
        self.assertEqual(report['model_views'],4);self.assertFalse(report['privacy_validated'])

    def test_reduction_is_view_order_independent_at_threshold(self):
        views=[np.array([[v]],np.float32) for v in [.4999999,.5000001,0.,1.]]
        expected=combine_restored_probabilities(views)
        for k in range(4):np.testing.assert_array_equal(expected,combine_restored_probabilities(views[k:]+views[:k]))

    def test_wrong_shape_nan_inf_range_dtype_and_count_rejected(self):
        valid=np.full((3,5),.5,np.float32)
        for bad in [np.zeros((2,5),np.float32),valid.astype(np.float64),np.full((3,5),np.nan,np.float32),
                    np.full((3,5),np.inf,np.float32),np.full((3,5),1.01,np.float32)]:
            with self.assertRaises(ValueError):combine_restored_probabilities([valid,valid,valid,bad])
        with self.assertRaises(ValueError):combine_restored_probabilities([valid]*3)

    def test_mutating_predictor_is_rejected_and_original_is_preserved(self):
        arrays=self.fixture();before=[a.copy() for a in arrays]
        def bad(rgb,body,tip):
            rgb[:]=0;return np.zeros(body.shape,np.float32)
        with self.assertRaisesRegex(ValueError,'mutated_input'):predict_orbit(*arrays,bad)
        for a,b in zip(arrays,before):np.testing.assert_array_equal(a,b)


if __name__=='__main__':unittest.main()

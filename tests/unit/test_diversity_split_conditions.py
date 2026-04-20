from council.experiments.diversity_split.conditions import CONDITIONS


class TestConditions:
    def test_four_conditions_present(self):
        names = {c.name for c in CONDITIONS}
        assert names == {
            "same_model_same_role",
            "same_model_diff_role",
            "diff_model_same_role",
            "diff_model_diff_role",
        }

    def test_same_model_cells_share_the_same_roster(self):
        by = {c.name: c for c in CONDITIONS}
        assert by["same_model_same_role"].roster == by["same_model_diff_role"].roster
        assert by["diff_model_same_role"].roster == by["diff_model_diff_role"].roster

    def test_same_role_cells_share_the_same_pack(self):
        by = {c.name: c for c in CONDITIONS}
        assert by["same_model_same_role"].pack == by["diff_model_same_role"].pack
        assert by["same_model_diff_role"].pack == by["diff_model_diff_role"].pack

    def test_model_axis_actually_differs_across_rosters(self):
        by = {c.name: c for c in CONDITIONS}
        same_models = set(by["same_model_same_role"].roster.models.values())
        diff_models = set(by["diff_model_same_role"].roster.models.values())
        assert len(same_models) == 1  # all slots identical
        assert len(diff_models) == 3  # all slots distinct

    def test_role_axis_actually_differs_across_packs(self):
        by = {c.name: c for c in CONDITIONS}
        bare = by["same_model_same_role"].pack
        roles = by["same_model_diff_role"].pack
        assert bare.personas == {}
        assert len(roles.personas) == 3
        # Three distinct persona strings.
        assert len(set(roles.personas.values())) == 3

    def test_same_model_arm_matches_homogenisation_homogeneous(self):
        # Cell A uses the same model across slots as the existing probe
        # so results are directly comparable.
        from council.experiments.homogenisation.rosters import ROSTERS

        homogeneous = next(r for r in ROSTERS if r.name == "homogeneous")
        by = {c.name: c for c in CONDITIONS}
        assert by["same_model_same_role"].roster.models == homogeneous.models

    def test_diff_model_arm_matches_homogenisation_substituted(self):
        from council.experiments.homogenisation.rosters import ROSTERS

        substituted = next(r for r in ROSTERS if r.name == "substituted")
        by = {c.name: c for c in CONDITIONS}
        assert by["diff_model_same_role"].roster.models == substituted.models

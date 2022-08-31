import pytest

# The hardware class has register assertion helpers that should be rewritten.
pytest.register_assert_rewrite("roadtest.core.hardware")

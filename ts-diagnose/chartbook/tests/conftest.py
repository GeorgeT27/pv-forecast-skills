"""chartbook 测试公共 conftest:集中豁免本环境唯一允许的警告——
anaconda 下 shap(Intel OpenMP)与 sklearn(LLVM OpenMP)同进程双载的
RuntimeWarning(环境产物,Plan3 T3 裁定接受)。此外任何警告都该在 -W error
下炸,新警告=回归。"""
import pytest

_OMP = "ignore:(?s).*Found Intel OpenMP.*LLVM OpenMP.*:RuntimeWarning"


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.filterwarnings(_OMP))

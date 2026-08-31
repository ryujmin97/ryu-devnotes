"""
175차: long_mpc.py의 실제 acados 솔버를 이 컨테이너에서 import/사용하기 위한
경량 스텁 모듈. openpilot 전체 스택(하드웨어 IPC, 캘리브레이션, 전체 차량 DB 등)을
끌고 오지 않고 long_mpc.py의 import 체인만 통과시키는 목적.

사용법 (build_acados_long_mpc.sh 로 빌드 완료 후):
    exec(open('/home/claude/devnotes/toolkit/acados_stub_prelude.py').read())
    from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc
    mpc = LongitudinalMpc(mode='acc')

주의: 이 스텁은 Params/messaging/Events를 전부 no-op으로 대체하므로,
LongitudinalMpc의 set_weights()/update()/run() 등 solver 계산 자체는 정상 동작하지만
실제 파라미터(Params) 값에 의존하는 분기는 전부 기본값/None으로 흐른다.
재현 시뮬레이션 작성 시 필요한 값(A_CHANGE_COST 등)은 직접 주입해야 함.
"""
import sys, types

# --- stub openpilot.common.params_pyx (컴파일된 Cython ext 불필요하게) ---
m = types.ModuleType("openpilot.common.params_pyx")
class _Params:
    def __init__(self, *a, **k): pass
    def get(self, *a, **k): return None
    def put(self, *a, **k): pass
    def check_key(self, *a, **k): return True
class _ParamKeyFlag: pass
class _ParamKeyType: pass
class _UnknownKeyName(Exception): pass
m.Params = _Params; m.ParamKeyFlag = _ParamKeyFlag; m.ParamKeyType = _ParamKeyType; m.UnknownKeyName = _UnknownKeyName
sys.modules["openpilot.common.params_pyx"] = m

# --- stub opendbc.car.interfaces (전체 차량 DB import 회피) ---
m2 = types.ModuleType("opendbc.car.interfaces")
m2.ACCEL_MIN = -4.0
sys.modules["opendbc.car.interfaces"] = m2

# --- stub cereal.messaging (컴파일된 msgq.ipc_pyx IPC ext 불필요하게) ---
class _Dummy:
    def __init__(self, *a, **k): pass
    def __getattr__(self, name): return lambda *a, **k: None
m3 = types.ModuleType("cereal.messaging")
m3.SubMaster = _Dummy; m3.PubMaster = _Dummy
m3.new_message = lambda *a, **k: None
m3.log_from_bytes = lambda *a, **k: None
sys.modules["cereal.messaging"] = m3

# --- stub selfdrived.events (transformations.pyx / calibrationd 체인 회피) ---
m4 = types.ModuleType("openpilot.selfdrive.selfdrived.events")
class _Events(_Dummy): pass
m4.Events = _Events
sys.modules["openpilot.selfdrive.selfdrived.events"] = m4
sys.modules["openpilot.selfdrive.selfdrived"] = types.ModuleType("openpilot.selfdrive.selfdrived")

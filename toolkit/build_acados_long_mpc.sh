#!/usr/bin/env bash
# 175차: long_mpc.py의 실제 acados 솔버를 이 컨테이너(x86_64, 사전빌드 acados 라이브러리
# third_party/acados/x86_64/ 존재 전제)에서 코드젠+컴파일해서 실사용 가능하게 만드는 절차.
# 컨테이너는 세션마다 리셋되므로 매 세션 재실행 필요 (총 소요 1~2분 내외).
#
# 사용법:
#   bash /home/claude/devnotes/toolkit/build_acados_long_mpc.sh
# 성공 시 아래로 바로 테스트:
#   export LD_LIBRARY_PATH=/home/claude/ryu/third_party/acados/x86_64/lib
#   export PYTHONPATH=/home/claude/ryu
#   python3 -c "
#   exec(open('/home/claude/devnotes/toolkit/acados_stub_prelude.py').read())
#   from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc
#   mpc = LongitudinalMpc(mode='acc')
#   print(mpc.solver)
#   "
#
# 전제: ryu repo가 /home/claude/ryu 에 clone돼 있음 (session init 절차로 이미 됨).
# 전제: pip install --break-system-packages -q setproctitle smbus2 pyzmq casadi cython future-fstrings
#       (이 스크립트 맨 앞에서 자동 설치함)

set -e

pip install --break-system-packages -q setproctitle smbus2 pyzmq casadi cython future-fstrings

ln -sfn /home/claude/ryu /home/claude/openpilot

MPC_DIR=/home/claude/ryu/selfdrive/controls/lib/longitudinal_mpc_lib
STUB=/home/claude/devnotes/toolkit/acados_stub_prelude.py

# --- 1) acados OCP 코드젠 (long_mpc.py 를 __main__ 으로 실행) ---
cd "$MPC_DIR"
export ACADOS_SOURCE_DIR=/home/claude/ryu/third_party/acados
export ACADOS_PYTHON_INTERFACE_PATH=/home/claude/ryu/third_party/acados/acados_template
export TERA_PATH=/home/claude/ryu/third_party/acados/x86_64/t_renderer
export LD_LIBRARY_PATH=/home/claude/ryu/third_party/acados/x86_64/lib
export PYTHONPATH=/home/claude/ryu:/home/claude/ryu/third_party/acados

python3 -c "
exec(open('$STUB').read())
import runpy, sys
sys.argv = ['long_mpc.py']
runpy.run_path('long_mpc.py', run_name='__main__')
"

echo "=== 1) codegen done, c_generated_code/ 생성됨 ==="

# --- 2) acados solver C코드 -> libacados_ocp_solver_long.so ---
cd "$MPC_DIR/c_generated_code"
ACADOS_INC=/home/claude/ryu/third_party/acados/include
ACADOS_LIB=/home/claude/ryu/third_party/acados/x86_64/lib

gcc -shared -fPIC -O2 -DACADOS_WITH_QPOASES -Wno-unused \
  -I. -I${ACADOS_INC} -I${ACADOS_INC}/acados -I${ACADOS_INC}/blasfeo/include -I${ACADOS_INC}/hpipm/include -I${ACADOS_INC}/qpOASES_e -I${ACADOS_INC}/qpOASES_e/include \
  acados_solver_long.c \
  long_model/long_expl_ode_fun.c long_model/long_expl_vde_forw.c \
  long_cost/long_cost_y_fun.c long_cost/long_cost_y_fun_jac_ut_xt.c long_cost/long_cost_y_hess.c \
  long_cost/long_cost_y_e_fun.c long_cost/long_cost_y_e_fun_jac_ut_xt.c long_cost/long_cost_y_e_hess.c \
  long_cost/long_cost_y_0_fun.c long_cost/long_cost_y_0_fun_jac_ut_xt.c long_cost/long_cost_y_0_hess.c \
  long_constraints/long_constr_h_fun.c long_constraints/long_constr_h_fun_jac_uxt_zt.c \
  -L${ACADOS_LIB} -Wl,-rpath,${ACADOS_LIB} -Wl,--disable-new-dtags \
  -lacados -lhpipm -lblasfeo -lqpOASES_e -lm \
  -o libacados_ocp_solver_long.so

echo "=== 2) libacados_ocp_solver_long.so 컴파일 완료 ==="

# --- 3) cython 바인딩: pyx -> c -> so ---
cython -o acados_ocp_solver_pyx.c -I . -I /home/claude/ryu/third_party/acados/acados_template \
  /home/claude/ryu/third_party/acados/acados_template/acados_ocp_solver_pyx.pyx

PYINC=$(python3 -c "import sysconfig; print(sysconfig.get_paths()['include'])")
NPINC=$(python3 -c "import numpy; print(numpy.get_include())")

gcc -shared -fPIC -O2 -DACADOS_WITH_QPOASES -Wno-unused \
  -I. -I${PYINC} -I${NPINC} -I${ACADOS_INC} -I${ACADOS_INC}/acados -I${ACADOS_INC}/blasfeo/include -I${ACADOS_INC}/hpipm/include \
  acados_ocp_solver_pyx.c \
  -L. -Wl,-rpath,'$ORIGIN' -Wl,-rpath,${ACADOS_LIB} -Wl,--disable-new-dtags \
  -lacados_ocp_solver_long -L${ACADOS_LIB} -lacados -lhpipm -lblasfeo -lqpOASES_e -lm \
  -o acados_ocp_solver_pyx.so

touch __init__.py
touch "$MPC_DIR/__init__.py"

echo "=== 3) acados_ocp_solver_pyx.so 컴파일 완료 ==="
echo "=== 빌드 전체 완료. 아래로 즉시 테스트 가능 ==="
echo 'export LD_LIBRARY_PATH=/home/claude/ryu/third_party/acados/x86_64/lib'
echo 'export PYTHONPATH=/home/claude/ryu'

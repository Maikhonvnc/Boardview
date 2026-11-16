# Caminhos centrais. Antes cada script tinha o caminho da maquina antiga cravado;
# agora BV vem do proprio arquivo e DRONES e descoberto (ou vem de BOARDVIEW_DRONES).
import os

BV = os.path.dirname(os.path.abspath(__file__))          # raiz do repo Boardview

def _norm(p):
    return p.replace(os.sep, '/')

def _achar_drones():
    env = os.environ.get('BOARDVIEW_DRONES')
    if env and os.path.isdir(env):
        return _norm(env)
    home = os.path.expanduser('~')
    cands = [os.path.join(home, 'Pictures', 'Drones', 'Drones'),
             os.path.join(home, 'Downloads', 'Drones'),
             os.path.join(home, 'Pictures', 'Drones'),
             os.path.join(os.path.dirname(BV), 'Drones')]
    for c in cands:
        # a raiz certa e a que contem pastas de modelo com .pcb dentro
        if os.path.isdir(c) and any(f.lower().endswith('.pcb')
                                    for _, _, fs in os.walk(c) for f in fs):
            return _norm(c)
    return _norm(cands[0])

DRONES = _achar_drones()
REFERENCIAS = os.path.join(BV, 'Referencias')
DV_BUILD = os.path.join(BV, 'digital_viewer', 'build')
DIGITALBOARD = os.path.join(BV, 'DigitalBoard')

if __name__ == '__main__':
    import sys
    if '--drones' in sys.argv:        # usado pelos .bat
        print(DRONES.replace('/', os.sep))
    else:
        print('BV     =', BV)
        print('DRONES =', DRONES)

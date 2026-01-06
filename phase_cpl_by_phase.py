import glob
import re
import json

def main():
    files = glob.glob('phase2_results.txt') + glob.glob('IMPROVEMENTS_COMPLETE.md')
    phase_cpls = {'opening': [], 'middlegame': [], 'endgame': []}
    pat = re.compile(r'By Phase:\n(.*?)Coach Summary:', re.S)
    for f in files:
        with open(f, 'r') as fh:
            d = fh.read()
        for m in pat.findall(d):
            for line in m.splitlines():
                if ':' in line:
                    ph = line.split(':')[0].strip().lower()
                    if ph in phase_cpls:
                        try:
                            cpl = line.split('CPL=')[1].split('cp')[0].strip()
                            if cpl != 'N/A':
                                phase_cpls[ph].append(int(cpl))
                        except Exception:
                            pass
    res = {k: (sum(v)/len(v) if v else 0) for k, v in phase_cpls.items()}
    print(json.dumps(res, indent=2))

if __name__ == '__main__':
    main()

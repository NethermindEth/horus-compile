import glob
import json
from io import StringIO
from os.path import exists

from horus.compiler.horus_compile import main


def test_golden(capsys):
    def run_horus_compile(file):
        main([file])
        out = capsys.readouterr().out
        program_json = json.loads(out)
        with StringIO() as checks_out:
            output = {
                "specifications": program_json["specifications"],
                "invariants": program_json["invariants"],
                "storage_vars": program_json["storage_vars"],
            }
            json.dump(output, checks_out, indent=2, sort_keys=True)
            return checks_out.getvalue()

    for file in glob.glob("./tests/golden/*.cairo"):
        with capsys.disabled():
            print(file)
        gold_name = file.replace(".cairo", ".gold")
        if not exists(gold_name):
            out = run_horus_compile(file)
            with open(gold_name, "w") as f:
                f.write(out)
        else:
            with open(gold_name, "r") as gold:
                text = gold.read()
            out = run_horus_compile(file)
            assert text == out

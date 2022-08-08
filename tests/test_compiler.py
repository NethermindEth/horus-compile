import glob
import json
import sys
from io import StringIO
from os.path import exists

import marshmallow_dataclass

from horus.compiler.contract_definition import HorusDefinition
from horus.compiler.horus_compile import main


def test_golden(capsys, monkeypatch):
    def run_horus_compile():
        main()
        out = capsys.readouterr().out
        program_json = json.loads(out)
        with StringIO() as checks_out:
            output = {
                "specifications": program_json["specifications"],
                "invariants": program_json["invariants"],
            }
            json.dump(output, checks_out, indent=2, sort_keys=True)
            return checks_out.getvalue()

    with monkeypatch.context() as m:
        for file in glob.glob("./tests/golden/*.cairo"):
            with capsys.disabled():
                print(file)
            gold_name = file.replace(".cairo", ".gold")
            if not exists(gold_name):
                m.setattr(sys, "argv", ["", file])
                out = run_horus_compile()
                with open(gold_name, "w") as f:
                    f.write(out)
            else:
                with open(gold_name, "r") as gold:
                    text = gold.read()

                m.setattr(
                    sys,
                    "argv",
                    [
                        "",
                        file,
                    ],
                )

                out = run_horus_compile()
                assert text == out


def test_division(monkeypatch):
    with monkeypatch.context() as m:
        for file in glob.glob("./tests/division/*.cairo"):
            m.setattr(
                sys,
                "argv",
                [
                    "",
                    file,
                ],
            )
            main()

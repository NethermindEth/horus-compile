import glob
import sys
from os.path import exists

from horus.compiler.horus_compile import main


def test_golden(monkeypatch):
    with monkeypatch.context() as m:
        for file in glob.glob("./tests/golden/*.cairo"):
            print(file)
            gold_name = file.replace(".cairo", ".gold")
            if not exists(gold_name):
                m.setattr(sys, "argv", ["", file, "--output", gold_name])
                main()
            else:
                with open(gold_name, "r") as gold:
                    text = gold.read()

                output_name = file.replace("./tests/golden", "./out").replace(
                    ".cairo", ".json"
                )
                m.setattr(
                    sys,
                    "argv",
                    [
                        "",
                        file,
                        "--output",
                        output_name,
                    ],
                )
                main()
                with open(
                    output_name,
                    "r",
                ) as f:
                    out = f.read()
                    assert text == out


def test_division(monkeypatch):
    with monkeypatch.context() as m:
        for file in glob.glob("./tests/division/*.cairo"):
            output_name = file.replace("./tests/division", "./out").replace(
                ".cairo", ".json"
            )
            m.setattr(
                sys,
                "argv",
                [
                    "",
                    file,
                    "--output",
                    output_name,
                ],
            )
            main()

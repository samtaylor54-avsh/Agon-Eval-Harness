# Your Eval (copy-me template)

Copy this folder somewhere and edit it to build your own Agon eval. Do it in this order:

1. **`dataset.yaml`** -- write your test cases (the only required step). Each case has an
   `input.user_message`, an `expected` block, and one or more `scoring` specs. Start with the
   built-in `keyword_containment` scorer so it runs with no code:

   ```bash
   uv run agon run dataset.yaml --display none
   ```

2. **`scorer.py`** *(optional)* -- if no built-in scorer fits, write your own. Edit the `# TODO`s,
   rename `my_scorer`, and reference it in `dataset.yaml` (`type: my_scorer`). Run it via the
   plugin loader (no need to fork agon):

   ```bash
   uv run agon run --plugin scorer.py dataset.yaml --display none
   ```

3. **`test_scorer.py`** -- every scorer earns a boundary test (a pass case and a fail case).
   Run it from this folder: `uv run pytest test_scorer.py`.

4. **`sut_adapter.py` + `run.py`** *(optional)* -- to evaluate **your** system instead of the mock,
   put it behind `my_sut` and drive the whole eval from Python (the CLI can't wire a callable):

   ```bash
   uv run python run.py
   ```

See `docs/extending.md` for the full contract of each extension point, and
`examples/text_to_sql/` for a complete worked example with a real custom scorer.

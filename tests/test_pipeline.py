import json
from pathlib import Path

import pandas as pd

from scorecard.adapters.base import TARGET
from scorecard.cli import main
from scorecard.config import config_from_dict
from scorecard.pipeline import run


def test_end_to_end_synthetic(small_config):
    result = run(small_config)
    out = Path(small_config.output.dir)
    v = result.primary
    assert 3 <= len(v.selected) <= 12
    assert "noise_feature" not in v.selected and "mostly_missing" not in v.selected
    lr = v.metrics[v.metrics["model"] == "LR scorecard"].set_index("segment")
    for seg in ("train", "test", "oot"):
        assert 0.6 < lr.loc[seg, "auc"] < 0.95 and 0.15 < lr.loc[seg, "ks"] < 0.9
    assert (v.coef_table["coefficient"].iloc[1:] < 0).all()
    assert v.cv["lr"]["cv_auc_mean"] > 0.6
    assert 0.01 < result.frame[TARGET].mean() < 0.4

    html = (out / "report.html").read_text(encoding="utf-8")
    md = (out / "report.md").read_text(encoding="utf-8")
    for heading in ("1. 样本与数据概况", "2. 分箱与 IV", "3. 模型表现", "4. 评分卡", "5. 策略分析", "6. 稳定性", "7. 自动检查与风险提示"):
        assert heading in html and heading in md
    assert html.count("（本阶段未实现）") >= 3  # sections 5-7 are visible placeholders in Phase 1
    assert "NaN" not in md and "nan" not in md.replace("nanoseconds", "")
    for name in ("results.json", "scorecard.csv", "iv_table.csv", "sample_definition.csv", "field_audit.csv", "scorecard_model.json", "run_meta.json"):
        assert (out / name).exists()
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert results["variants"]["no_platform_rating"]["n_selected"] == len(v.selected)
    assert (out / "figures").is_dir() and len(list((out / "figures").glob("*.png"))) >= 6
    # sample-definition log is in the report
    sample_log = pd.read_csv(out / "sample_definition.csv")
    assert list(sample_log["rule"]) == [r["rule"] for r in result.meta.sample_definition_log]


def test_platform_rating_variant_adds_grade(small_config):
    small_config.features.use_platform_rating = True
    small_config.model.cv_folds = 2
    result = run(small_config, render=False)
    v = result.primary
    assert v.name == "with_platform_rating" and "grade" in v.candidate_features


def test_cli_runs_synthetic_config(tmp_path, capsys):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "dataset:\n  adapter: synthetic\n  options: {n_rows: 4000, n_months: 24}\nsample:\n  min_issue_date: null\n"
        "binning: {backend: tree, sample_size: 4000}\nmodel: {cv_folds: 2, cv_challenger: false, gbdt: {max_iter: 40}}\n"
        f"report: {{embed_figures: false}}\noutput: {{dir: '{(tmp_path / 'o').as_posix()}'}}\n",
        encoding="utf-8",
    )
    assert main(["run", "--config", str(cfg_path)]) == 0
    assert (tmp_path / "o" / "report.html").exists()
    assert "AUC" in capsys.readouterr().out


def test_generic_csv_adapter(tmp_path, synthetic_frame):
    csv = tmp_path / "loans.csv"
    frame = synthetic_frame.rename(columns={"target": "defaulted", "issue_date": "orig_date"}).drop(columns=["event_date", "net_cash"])
    frame["defaulted"] = frame["defaulted"].map({0: "no", 1: "yes"})
    frame.to_csv(csv, index=False)
    cfg = config_from_dict(
        {
            "dataset": {"adapter": "generic", "path": str(csv), "options": {"target_col": "defaulted", "positive_label": "yes", "date_col": "orig_date", "loan_amount_col": "loan_amount", "platform_rating_cols": ["grade"]}},
            "sample": {"min_issue_date": None},
            "binning": {"backend": "tree"},
            "model": {"cv_folds": 2, "cv_challenger": False, "gbdt": {"max_iter": 40}},
            "report": {"embed_figures": False},
            "output": {"dir": str(tmp_path / "g")},
        }
    )
    result = run(cfg, render=False)
    assert abs(result.frame[TARGET].mean() - synthetic_frame[TARGET].mean()) < 1e-9
    assert "grade" not in result.primary.candidate_features and result.meta.platform_rating_cols == ["grade"]


def test_html_report_escapes_markup(tmp_path):
    from jinja2 import Environment, PackageLoader

    from scorecard.report import md_table, table_block

    env = Environment(loader=PackageLoader("scorecard", "templates"), autoescape=lambda n: bool(n) and n.endswith(".html.j2"))
    assert env.autoescape("report.html.j2") is True and env.autoescape("report.md.j2") is False
    block = table_block(pd.DataFrame({"feature": ["<NA>", "R&D <script>x</script>"], "iv": [0.1, 0.2]}))
    html = env.get_template("report.html.j2").render(title="t", header=[], headline=[], warnings=[], placeholder="p", sections=[{"number": 1, "title": "s", "intro": "", "implemented": True, "blocks": [block]}])
    assert "&lt;script&gt;" in html and "<script>x</script>" not in html and "&lt;NA&gt;" in html
    assert "| <NA> |" in md_table(block)

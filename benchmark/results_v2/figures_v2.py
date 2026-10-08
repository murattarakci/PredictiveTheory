"""Figures A2 and A3 for the appendix, from the corrected (v2) benchmark.

Usage: python3 figures_v2.py <results_v2 dir> <output figure dir>
"""
import csv
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


rows = [r for r in csv.DictReader(open(os.path.join(src, "results_v2_final.csv")))]
for r in rows:
    for k in ("test_rmse", "val_rmse", "me_train", "se_train_cl", "me_val", "csp_contribution"):
        r[k] = num(r[k]) if r[k] not in ("NA", "") else None
scored = [r for r in rows if r["test_rmse"] is not None and r["val_rmse"] is not None]

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times"], "font.size": 10})
col = {"linear": "#4C72B0", "quadratic": "#DD8452", "moderation": "#55A868"}

# ---------------------------------------------------------------- Figure A2
roa = sorted([r for r in scored if r["dv"] == "mean_roa"], key=lambda r: r["test_rmse"])
mva = sorted([r for r in scored if r["dv"] == "mean_mva"], key=lambda r: r["test_rmse"])
fig, ax = plt.subplots(1, 3, figsize=(11, 3.7))
for k, (data, title) in enumerate([(roa, f"(a) ROA specifications (n = {len(roa)})"),
                                   (mva, f"(b) MVA specifications (n = {len(mva)})")]):
    for fam in ("linear", "quadratic", "moderation"):
        xs = [i for i, r in enumerate(data) if r["functional_form"] == fam]
        ax[k].scatter(xs, [data[i]["test_rmse"] for i in xs], s=5, color=col[fam], label=fam)
    ax[k].set_title(title)
    ax[k].set_xlabel("Specification, ranked by test RMSE")
    ax[k].set_ylabel("Test RMSE")
ax[0].legend(frameon=False, title="CSP term", fontsize=8, title_fontsize=8, markerscale=2)
top = roa[:50]
ax[2].scatter([r["test_rmse"] for r in roa[50:]], [r["val_rmse"] for r in roa[50:]], s=5, color="#999999",
              label="other ROA specifications")
ax[2].scatter([r["test_rmse"] for r in top], [r["val_rmse"] for r in top], s=10, color="#C44E52",
              label="50 best by test RMSE")
lo = min(min(r["test_rmse"], r["val_rmse"]) for r in roa)
hi = max(max(r["test_rmse"], r["val_rmse"]) for r in roa)
ax[2].plot([lo, hi], [lo, hi], lw=0.8, color="black", ls="--")
ax[2].set_title("(c) Test vs. validation RMSE, ROA")
ax[2].set_xlabel("Test RMSE")
ax[2].set_ylabel("Validation RMSE")
ax[2].legend(frameon=False, fontsize=8)
for a in ax:
    a.spines["top"].set_visible(False)
    a.spines["right"].set_visible(False)
plt.tight_layout()
plt.savefig(os.path.join(out, "figureA2_performance.png"), dpi=200)
plt.close()

# ---------------------------------------------------------------- Figure A3
x = list(range(1, len(top) + 1))
me = [r["me_train"] for r in top]
se = [r["se_train_cl"] for r in top]
fig, ax = plt.subplots(3, 1, figsize=(7.5, 8.2), sharex=True,
                       gridspec_kw={"height_ratios": [1.2, 1, 0.9]})
ax[0].vlines(x, [m - 1.96 * s for m, s in zip(me, se)], [m + 1.96 * s for m, s in zip(me, se)],
             color="#888888", lw=1)
ax[0].scatter(x, me, s=14, color="#1f4e9c", zorder=3, label="training firms (95% CI, clustered)")
ax[0].scatter(x, [r["me_val"] for r in top], s=16, marker="x", color="#C44E52", zorder=4, label="validation firms")
ax[0].legend(frameon=False, fontsize=8, loc="lower left", ncol=2); ax[0].set_ylim(-0.35, None)
ax[0].axhline(0, color="black", lw=0.8, ls="--")
ax[0].set_ylabel("Marginal effect of\nCSP on ROA")
ax[1].plot(x, [r["test_rmse"] for r in top], marker="o", ms=3, lw=1, color="#C44E52", label="Test RMSE")
ax[1].plot(x, [r["val_rmse"] for r in top], marker="s", ms=3, lw=1, color="#55A868", label="Validation RMSE")
ax[1].set_ylabel("RMSE")
ax[1].legend(frameon=False, fontsize=8)
bt = {r["spec_id"]: r for r in csv.DictReader(open(os.path.join(src, "top50_roa_final.csv")))}
cc = [float(bt[r["spec_id"]]["point"]) for r in top]
clo = [float(bt[r["spec_id"]]["lo"]) for r in top]
chi = [float(bt[r["spec_id"]]["hi"]) for r in top]
ax[2].vlines(x, clo, chi, color="#888888", lw=1)
ax[2].scatter(x, cc, s=14, color=["#1f4e9c" if c > 0 else "#C44E52" for c in cc], zorder=3)
ax[2].axhline(0, color="black", lw=0.8)
ax[2].set_ylabel("Validation RMSE gain\nfrom CSP terms (95% CI)")
ax[2].set_xlabel("Specification, ranked by test RMSE")
for a in ax:
    a.spines["top"].set_visible(False)
    a.spines["right"].set_visible(False)
plt.tight_layout()
plt.savefig(os.path.join(out, "figureA3_top50.png"), dpi=200)
print("figures written to", out)

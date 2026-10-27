"""Render saved replay histograms without rerunning selection or sampling."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports',nargs='+')
    parser.add_argument('--output',required=True)
    parser.add_argument('--preview')
    args=parser.parse_args()
    plt.rcParams.update({'svg.fonttype':'none','font.family':'DejaVu Sans','font.size':10})
    fig,axes=plt.subplots(1,len(args.reports),figsize=(11,4.5),squeeze=False)
    for ax,path in zip(axes.flat,args.reports):
        report=json.loads(Path(path).read_text())
        hist=report['random_roi_histogram']
        edges=np.asarray(hist['edges']);counts=np.asarray(hist['counts'])
        shown=edges[:-1]<100
        ax.bar(edges[:-1][shown],100*counts[shown]/report['random_draws'],
               width=np.diff(edges)[shown],align='edge',color='#8aa6bc',edgecolor='white')
        ax.axvline(report['random_roi_median'],color='#526271',ls='--',lw=1.6,label='Random median')
        ax.axvline(report['replay_roi_pct'],color='#008977',lw=2.4,
                   label=f"Selected: {report['replay_roi_pct']:+.1f}% ROI")
        ax.set(xlim=(-102,101),xlabel='Realized ROI (%)',ylabel='Random portfolios per bin (%)')
        title=report['platform']+(' — provisional payouts' if report['platform']=='FanDuel' else '')
        ax.set_title(title,loc='left',fontsize=11,fontweight='bold')
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
        tail=int(counts[~shown].sum())
        ax.text(.98,.96,f"MC comparison: {report['replay_one_sided_mc_p']:.4f}\n{tail:,} draws at/above +100% outside view",
                transform=ax.transAxes,ha='right',va='top',fontsize=8.5)
        ax.legend(loc='upper right',bbox_to_anchor=(1,.80),frameon=False,fontsize=8.5)
    fig.suptitle('Frozen selection versus 10,000 constrained random portfolios',x=.06,ha='left',fontsize=13,fontweight='bold')
    fig.text(.06,.025,'DAL–PHI, Oct 26, 2026 · Development replay · Same-game results are correlated; no prospective edge established.',fontsize=9,color='#425466')
    fig.tight_layout(rect=(.02,.075,1,.91))
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(output)
    if args.preview:
        fig.savefig(args.preview,dpi=150)
    plt.close(fig)


if __name__=='__main__':
    main()

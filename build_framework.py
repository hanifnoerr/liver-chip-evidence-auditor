"""Draw the implemented numerical, action-selection and reassessment mechanisms."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.font_manager import FontProperties

ROOT = Path(__file__).resolve().parent
matplotlib.rcParams["svg.fonttype"] = "none"
matplotlib.rcParams["font.family"] = "DejaVu Sans"
COLOURS = {"ink":"#1b1b1b", "navy":"#162e51", "blue":"#1a4480", "line":"#565c65", "neutral":"#f0f0ec", "tint":"#ecf1f7", "gold":"#f5f0e6", "amber":"#5c410a"}


def canvas(height, title, subtitle):
    figure = plt.figure(figsize=(6.85, height/100))
    axes = figure.add_axes([0,0,1,1])
    axes.set_xlim(0,685)
    axes.set_ylim(0,height)
    axes.axis("off")
    axes.text(20,height-32,title,fontsize=15,fontweight="bold",color=COLOURS["navy"])
    axes.text(20,height-57,subtitle,fontsize=9.4,color=COLOURS["ink"])
    return figure,axes


def label(axes,x,y,text):
    axes.text(x,y,text,fontsize=11.4,fontweight="bold",color=COLOURS["navy"])


def box(axes,x,y,width,height,title,lines,tone="neutral",size=9.4):
    patch=FancyBboxPatch((x,y),width,height,boxstyle="round,pad=0,rounding_size=6",linewidth=0.9,edgecolor=COLOURS["line"],facecolor=COLOURS[tone])
    axes.add_patch(patch)
    renderer = axes.figure.canvas.get_renderer()

    def wrap(text, font_size, weight="normal"):
        properties = FontProperties(size=font_size, weight=weight)
        if text.startswith("$"):
            return [text]
        result, current = [], ""
        for word in text.split():
            candidate = (current+" "+word).strip()
            measured = renderer.get_text_width_height_descent(candidate, properties, ismath=candidate.startswith("$"))[0] / axes.figure.dpi * 100
            if current and measured > width-24:
                result.append(current)
                current = word
            else:
                current = candidate
        return result+[current]

    title_lines=wrap(title,10.4,"bold")
    cursor=y+height-24
    for line in title_lines:
        artist = axes.text(x+12,cursor,line,fontsize=10.4,fontweight="bold",color=COLOURS["navy"])
        artist._framework_bounds = (x+10,y+4,x+width-10,y+height-4)
        cursor-=19
    cursor-=5
    for line in lines:
        for wrapped in wrap(line,size):
            artist = axes.text(x+12,cursor,wrapped,fontsize=size,color=COLOURS["ink"])
            artist._framework_bounds = (x+10,y+4,x+width-10,y+height-4)
            cursor-=26 if wrapped.startswith("$") else 18
    if lines and cursor+18 < y+8:
        raise ValueError(f"Figure box is too short: {title}; last baseline {cursor+18-y:.1f}")


def arrow(axes,points,dashed=False):
    for start,end in zip(points[:-2],points[1:-1]):
        axes.plot([start[0],end[0]],[start[1],end[1]],color=COLOURS["blue"],linewidth=1.1,linestyle="--" if dashed else "-")
    axes.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle="-|>",mutation_scale=9,linewidth=1.1,color=COLOURS["blue"],linestyle="--" if dashed else "-"))


def save(figure,name):
    figure.canvas.draw()
    axes = figure.axes[0]
    for artist in axes.texts:
        bounds = getattr(artist,"_framework_bounds",(0,0,685,axes.get_ylim()[1]))
        extent = artist.get_window_extent(figure.canvas.get_renderer()).transformed(axes.transData.inverted())
        if extent.x0 < bounds[0] or extent.y0 < bounds[1] or extent.x1 > bounds[2] or extent.y1 > bounds[3]:
            raise ValueError(f"Text exceeds its figure region: {artist.get_text()}")
    for extension in ["svg","pdf","png"]:
        figure.savefig(ROOT/(name+"."+extension),dpi=240,facecolor="white")
    plt.close(figure)


def numerical_framework():
    figure,axes=canvas(930,"Liver-Chip Evidence Auditor","Figure 1. Original endpoint evidence → numerical inference → source-linked concerns")
    label(axes,20,847,"A. Per-compound source gate and fitted response")
    box(axes,20,645,205,180,"Original records R0",["Day-three albumin (%)","R0: one compound","6 drugs / 35 conditions","Dataset: 68 observed, 2 NA","Workbook-cell source IDs","Chip/run/donor unknown","C12: 69.68% at 300x"])
    box(axes,245,645,190,180,"Fixed source gate",["Original measurements","Unique source-record IDs","Positive finite doses","Compatible dose/response","units; day 3; one drug","Invalid input blocks F(R0)"])
    box(axes,455,645,210,180,"Observed-count PAVA",["Dose means m_j, counts n_j","Non-increasing values z_j",r"$\min_{\mathbf{z}}\ \sum_{j=1}^{J} n_j(z_j-m_j)^2$",r"$z_j\geq z_{j+1},\ j=1,\ldots,J-1$","Log-dose interpolation","50% crossing or censoring"],"tint")
    arrow(axes,[(225,735),(245,735)])
    arrow(axes,[(435,735),(455,735)])
    label(axes,20,603,"B. Finite sensitivity around the original fit A0")
    arrow(axes,[(560,645),(675,645),(675,575),(94,575),(94,560)])
    axes.plot([94,590],[575,575],color=COLOURS["blue"],linewidth=1.1)
    for centre in [258,424,590]:
        arrow(axes,[(centre,575),(centre,560)])
    box(axes,20,370,148,190,"Alternative curves",["Raw dose means","4-parameter","logistic fit","Compare with A0","Constant baseline:","comparison only"],"gold")
    box(axes,184,370,148,190,"Reading deletion",["Delete 1 observed","if another remains","at that dose","Refit same PAVA","Measure influence;","retain original R0"],"gold")
    box(axes,350,370,148,190,"Dose deletion",["Delete 1 condition","Keep >= 2 doses","Refit same PAVA","Track remaining","range and loss of","bracketing"],"gold")
    box(axes,516,370,149,190,"Missing probes",["Replace 1 missing","with 0, 50, 100,","150 or 200%","Refit same PAVA","Hypothetical values;","not imputation"],"gold")
    for centre in [94,258,424,590]:
        arrow(axes,[(centre,370),(centre,345)])
    axes.plot([94,590],[345,345],color=COLOURS["blue"],linewidth=1.1)
    arrow(axes,[(342,345),(342,327)])
    box(axes,20,248,645,79,"Material conclusion change",["Different crossing/censoring state OR a finite crossing-location ratio > 2x","Diagnostics are reported separately; scenario agreement is not a probability."],"tint")
    label(axes,20,220,"C. Audited evidence and deterministic source cards")
    arrow(axes,[(342,248),(342,240),(675,240),(675,207),(176,207),(176,195)])
    arrow(axes,[(509,207),(509,195)])
    box(axes,20,77,312,118,"Audit A0 = F(R0)",["Crossing, range and fitted alternatives","14 named checks and fit diagnostics","Pass / Fail / Not assessed","5 experimental checks: Not assessed"])
    box(axes,353,77,312,118,"Source-linked cards K0",["Source IDs, dose, scenario IDs and values","Card explains what changes and why","Summary E0 → planner (Fig. 2)","Full cards bypass model inference"],"tint")
    axes.text(20,47,"Real Clozapine example: full fit is right-censored; temporary deletion of C12",fontsize=9.4,color=COLOURS["ink"])
    axes.text(20,27,"gives 256.22x unbound Cmax. Influence does not establish an erroneous reading.",fontsize=9.4,color=COLOURS["ink"])
    save(figure,"framework")


def action_framework():
    figure,axes=canvas(870,"Source-specific action selection","Figure 2. Adaptation is separate from inference; scientific values bypass the model")
    label(axes,20,784,"A. Offline supervised adaptation of SmolLM2-135M")
    box(axes,20,631,205,132,"Policy targets",["728 train / 96 groups","182 validation / 24 groups","Group-separated requests","Authored heuristic labels"],"gold")
    box(axes,245,631,190,132,"Full adaptation",["134,515,008 parameters","Prompt loss is masked","Assistant code + EOS loss","3 epochs; AdamW 5e-5"],"tint")
    box(axes,455,631,210,132,"Epoch selection",["Lowest validation loss","Epoch 2: theta*","364 test / 48 groups","42 published requests"],"tint")
    arrow(axes,[(225,697),(245,697)])
    arrow(axes,[(435,697),(455,697)])
    label(axes,20,606,"B. Runtime inputs and engine choice")
    box(axes,20,400,312,187,"Prompt(E0, q, r)",["E0: state, crossing, measured dose range,","changed-scenario and concern counts","q: researcher request","r: review / repeat / archive / new dose","Eligible codes C(E0,r) are included","Full source cards are not prompt inputs"],"neutral")
    box(axes,353,400,312,187,"Optional model; fixed theta*",["One prompt prefill; reuse its KV cache","Score all eight action-code sequences",r"$S(c)=\frac{1}{|c|}\sum_t\log p_{\theta^*}(c_t\mid P,c_{<t})$","EOS excluded; scores are not confidence",r"$c_{raw}=\arg\max_c S(c)$"],"tint")
    arrow(axes,[(332,493),(353,493)])
    arrow(axes,[(560,631),(677,631),(677,496),(665,496)],True)
    axes.text(675,603,"theta*",fontsize=8.8,ha="right",color=COLOURS["blue"])
    box(axes,20,305,312,74,"Default request-aware rules",["c_raw = rule_action(E0, q, r)","Apply authored intent and resource policy"])
    box(axes,353,305,312,74,"Original source cards K0",["Dose / values / workbook cells from Fig. 1","Bypass the model; supplied to renderer"])
    arrow(axes,[(176,400),(176,379)])
    arrow(axes,[(509,400),(509,392),(343,392),(343,295),(509,295),(509,282)])
    arrow(axes,[(176,305),(176,282)])
    box(axes,20,164,645,118,"Eligibility and scope guard",["Blocked input → FIX; recognised unsupported request → ABSTAIN","Resource-ineligible / forbidden code → request-aware fallback","Retain c_raw, c_delivered, eligible codes and fallback flag","Lexical checks do not guarantee protection for arbitrary new wording"],"gold")
    arrow(axes,[(342,164),(342,151)])
    arrow(axes,[(665,342),(677,342),(677,90),(665,90)])
    box(axes,20,37,645,114,"Deterministic card renderer and action snapshot",["c_delivered selects the first relevant K0 card; copy original evidence and limits","INSPECT example: ALBUMIN!C12, 300x, 69.68%, deletion crossing 256.22x","No generated measurement, optimal dose or scientific citation","Snapshot is retained before source inspection or outcome recording (Fig. 3)"],"tint")
    axes.text(20,15,"Codes: FIX / INSPECT / REPEAT / RECOVER / COMPARE / EXTEND / REPORT / ABSTAIN",fontsize=8.9,color=COLOURS["ink"])
    save(figure,"action_framework")


def followthrough_framework():
    figure,axes=canvas(830,"Outcome recording and evidence reassessment","Figure 3. Notes document a decision; a compatible CSV starts a separate evidence version")
    box(axes,20,642,645,116,"Preserved action snapshot P0",["R0 records + audit A0 + request/resources + raw/delivered action + inference","Match the evidence version using sorted record contents; workflow ID is not a chip ID","Save the draft before leaving to inspect workbook-linked measurements","Original records and earlier plans remain available in exported history"],"tint")
    arrow(axes,[(342,642),(342,622),(176,622),(176,602)])
    arrow(axes,[(342,622),(509,622),(509,602)])
    box(axes,20,414,312,188,"Notes-only outcome",["Record findings and source reference","Pending / inspected / unresolved / reported","Append outcome to P0","Measurements and A0 stay unchanged","Computed warnings stay unchanged","No laboratory validity is inferred"])
    box(axes,353,414,312,188,"Updated CSV R1 + documentation",["Complete case + reference + compatibility","Same compound, day 3 and normalised units","Keep every baseline source-record ID","Observed originals cannot become missing","Reject duplicates or derived observations","Unknown chip/run/donor IDs remain unknown"],"gold")
    arrow(axes,[(509,414),(509,393)])
    box(axes,353,229,312,164,"Action-specific update gate",["RECOVER: missing baseline ID → observed","REPEAT: new ID at the named existing dose","EXTEND: new ID at a new observed dose","FIX: blocked baseline → usable revised input","INSPECT: documented evidence revision","Metadata alone is not a new measurement"],"gold")
    arrow(axes,[(509,229),(509,213)])
    box(axes,353,85,312,128,"Re-audit with unchanged F",["Recompute A0 = F(R0), A1 = F(R1)","Record changes and check changes","Crossing state, location and range","Compatibility: researcher report","Authenticity is not verified"],"tint")
    arrow(axes,[(176,414),(176,390)])
    box(axes,20,208,312,182,"Action and outcome history",["P0 + recorded outcomes + A1 if supplied","R0 is retained beside R1","One reassessment per action","Rejected CSV preserves the prior record","Store only in this browser tab's session","Export JSON before closing the tab"],"neutral")
    arrow(axes,[(353,147),(342,147),(342,300),(332,300)])
    arrow(axes,[(176,208),(176,186)])
    box(axes,20,45,312,141,"Compare and continue",["Compare conclusions and record changes","List remaining failed/unassessed checks","Accepted R1 → updated Review","New action from A1; preserve P0","Notes never clear computed warnings"],"tint")
    axes.text(353,54,"CSV checks do not prove independent chips,",fontsize=9.4,color=COLOURS["ink"])
    axes.text(353,34,"assay validity or clinical drug safety.",fontsize=9.4,color=COLOURS["ink"])
    save(figure,"followthrough_framework")


if __name__ == "__main__":
    numerical_framework()
    action_framework()
    followthrough_framework()
    print("Created three editable SVGs, vector PDFs and PNG previews at the report's 174 mm width.")

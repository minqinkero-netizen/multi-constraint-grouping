"""Select a CJK font without requiring LaTeX or a repository-owned font copy."""
from pathlib import Path
import warnings

def configure(plt):
 from matplotlib import font_manager
 candidate=Path(__file__).resolve().parent.parent/'paper/fonts/NotoSansCJKsc-Regular.otf'
 if candidate.exists():font_manager.fontManager.addfont(str(candidate))
 installed={f.name for f in font_manager.fontManager.ttflist}
 choices=[x for x in ['Noto Sans CJK SC','Microsoft YaHei','SimHei','SimSun','Arial Unicode MS'] if x in installed]
 if not choices:warnings.warn('No CJK font found. Install Noto Sans CJK SC, Microsoft YaHei, or SimHei before plotting Chinese labels.')
 plt.rcParams.update({'font.family':choices+['DejaVu Sans'],'axes.unicode_minus':False})

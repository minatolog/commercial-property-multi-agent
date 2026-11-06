"""生成**合成**合同/制度 PDF（Task 011）。

为什么用 reportlab：
- 文档是中文，必须真正写出可被 PDF 解析器还原的中文字形；
- 手工拼装 PDF 内容流只能写 ASCII（`(中文) Tj` 会触发 UnicodeEncodeError），
  而 Helvetica 等标准字体也无法表示汉字；
- reportlab 能对系统 TTF 做子集嵌入并写 ToUnicode CMap，pypdf 可可靠取回中文。

字体策略（不把某台机器的路径当成唯一依赖）：
1. 优先探测常见中文字体文件（Windows / macOS / Linux 常见位置）；
2. 都找不到时退回 reportlab 自带的 Adobe CID 字体 `STSong-Light`（不嵌入，但仍是合法 PDF）。

**页码契约**：`CONTRACT_PAGES` 的下标 + 1 就是真实 PDF 页码。
fixture `document_snippets` 声明的页码（5.2 → p12、7.1 → p20、附件B → p26、物业 3.1 → p1）
必须与生成结果一致，否则"证据页码"会造假。测试 `test_rag.py` 会逐条比对。

内容全部是合成条款，不含任何真实合同文本。
"""

from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

__all__ = [
    "CONTRACT_PAGES",
    "POLICY_PAGES",
    "build_contract_pdf",
    "build_policy_pdf",
    "build_pdf",
    "resolve_font_name",
]

#: 星汇广场 A-301 合成租赁合同：26 页，页码与 fixture 的 document_snippets 对齐。
CONTRACT_PAGES: tuple[tuple[str, ...], ...] = (
    # p1
    (
        "租赁合同（合成样本）",
        "合同编号：XH-A301-2025-001（合成）",
        "出租方（甲方）：星汇广场置业（合成）",
        "承租方（乙方）：云端咖啡（合成）",
        "第一条 租赁标的",
        "1.1 甲方将星汇广场 A 座 A-301 商铺出租给乙方使用，建筑面积 120.00 平方米。",
        "1.2 租赁用途为餐饮，乙方不得擅自改变用途。",
    ),
    # p2
    (
        "1.3 乙方确认已在签约前查验商铺现状，除本合同另有约定外，甲方不承担额外装修义务。",
        "第二条 租赁期限",
        "2.1 租赁期限自 2025 年 1 月 1 日起至 2027 年 12 月 31 日止。",
        "2.2 租赁期限届满前三个月，双方应就是否续租进行书面协商。",
    ),
    # p3
    (
        "第三条 履约保证金",
        "3.1 乙方应按首年月租金标准向甲方缴付履约保证金，具体金额以双方确认的保证金收据为准。",
        "3.2 履约保证金不计入租金收入，亦不冲抵租金应收。",
        "3.3 履约保证金的收取、退还与抵扣适用独立的资金记录规则，不在本合同租金条款范围内处理。",
    ),
    # p4
    (
        "3.4 乙方发生违约情形时，甲方可依约从履约保证金中扣除相应款项，并书面通知乙方。",
        "3.5 租赁关系终止且乙方无欠缴款项、无未修复损坏时，甲方应退还履约保证金余额。",
    ),
    # p5
    (
        "第四条 交付与装修",
        "4.1 甲方应于 2024 年 12 月 20 日前将商铺按现状交付乙方，双方签署交付确认单。",
        "4.2 乙方装修方案须经甲方书面同意，并符合消防与商业综合体统一管理要求。",
    ),
    # p6
    (
        "4.3 装修施工时间为每日 22:00 至次日 06:00，不得影响其他商户正常经营。",
        "4.4 乙方不得改动商铺承重结构、消防通道及公共区域设施。",
    ),
    # p7
    (
        "4.5 装修工程验收合格后，乙方方可正式营业；未经验收擅自营业的，甲方有权要求停业整改。",
        "4.6 乙方装修投入的固定附着物，在租赁关系终止时无偿归甲方所有，双方另有约定的除外。",
    ),
    # p8
    (
        "4.7 甲方负责交付时商铺主体结构、给排水主管道及供电入户线路的正常可用。",
        "4.8 交付后商铺内部管线、设备的日常维护由乙方负责。",
    ),
    # p9
    (
        "4.9 因甲方原因导致交付延迟的，租赁期限相应顺延，甲方不承担其他赔偿责任。",
        "4.10 乙方不得将商铺用于存放易燃、易爆、剧毒等危险物品。",
    ),
    # p10
    (
        "第五条 租金及调整",
        "5.1 首年租金单价为每平方米每月 120.00 元，按月支付。",
        "5.1.1 月租金金额按建筑面积乘以当期租金单价计算，尾差按四舍五入保留至分。",
    ),
    # p11
    (
        "5.1.2 乙方应于每月五日前支付当月租金，逾期支付的按日万分之五计收违约金。",
        "5.1.3 租金以人民币结算，支付方式为银行转账至甲方指定账户。",
    ),
    # p12 —— fixture snip_contract_5_2 声明位于第 12 页
    (
        "5.2 自第二个租赁年度起，租金每十二（12）个月递增百分之五（5%）；递增基数为上一租赁年度末月租金标准。",
    ),
    # p13
    (
        "5.3 租金递增不以乙方是否收到书面通知为条件。",
        "5.4 甲方调整计租面积时，应提供测绘依据并提前三十日书面通知乙方。",
    ),
    # p14
    (
        "第六条 物业费",
        "6.1 物业费按建筑面积每平方米每月 18.00 元计收。",
        "6.2 物业费与租金分别计收，可合并出具账单，但收费项目应分项列示。",
    ),
    # p15
    (
        "6.3 公共区域水电、垃圾清运等费用按实际发生额或约定标准分摊。",
        "6.4 本合同项下能耗费用采用固定费用或人工抄表导入方式结算。",
    ),
    # p16
    (
        "6.5 甲方不得在合同期内单方面提高物业费标准，国家政策调整或双方书面约定的除外。",
        "6.6 乙方连续两个月未缴物业费的，甲方可按合同约定采取催缴措施。",
    ),
    # p17
    (
        "第七条 减免与审批",
        "7.0.1 本章所称减免，指对已产生或将要产生的租金、物业费应收款项的部分或全部豁免。",
        "7.0.2 减免事项属于重大经营决策，须留存申请、审批与执行全过程记录。",
    ),
    # p18
    (
        "7.0.3 减免申请的受理部门为物业管理部门，审批部门为财务部门。",
        "7.0.4 任何口头承诺、即时通讯工具中的表述均不构成有效减免依据。",
    ),
    # p19
    (
        "7.0.5 减免事项应建立台账，按月汇总并接受内部审计。",
        "7.0.6 减免生效后，已开具账单应通过调整或红冲方式处理，不得直接删除账单记录。",
    ),
    # p20 —— fixture snip_contract_7_1 声明位于第 20 页
    (
        "7.1 任何租金减免须由承租方书面提出申请，经物业管理部门与财务部门共同审批后生效；审批期间承租人仍应按原约定支付租金。",
    ),
    # p21
    (
        "第八条 维修与保养",
        "8.1 空调等设备故障报修后，甲方应在 24 小时内响应，48 小时内到场检修。",
    ),
    # p22
    (
        "8.2 因乙方使用不当造成的损坏，维修费用由乙方承担。",
        "8.3 因甲方设备老化导致的故障，维修费用由甲方承担。",
    ),
    # p23
    (
        "第九条 违约责任",
        "9.1 乙方逾期支付租金超过三十日的，甲方有权解除合同并要求乙方腾退商铺。",
    ),
    # p24
    (
        "9.2 甲方无正当理由提前收回商铺的，应赔偿乙方因此产生的直接损失。",
        "9.3 违约金总额以实际损失为限，双方另有约定的从其约定。",
    ),
    # p25
    (
        "第十条 其他约定",
        "10.1 本合同附件与正文具有同等效力。",
        "10.2 因本合同产生的争议，双方应先行协商；协商不成的，提交商铺所在地人民法院管辖。",
    ),
    # p26 —— fixture snip_contract_appendix_ref 声明位于第 26 页
    (
        "附件",
        "附件A《商铺交付确认单》为本合同组成部分，随交付环节签署。",
        "附件B《免租期与装修期补充约定》为本合同不可分割组成部分，与正文具有同等效力。",
        "（附件B 尚未电子化归档，本样本不含其内容。）",
    ),
)

#: 星汇广场物业报修响应标准（合成）：页码与 fixture 的 snip_property_policy_3_1（p1）对齐。
POLICY_PAGES: tuple[tuple[str, ...], ...] = (
    (
        "星汇广场物业报修响应标准（合成样本）",
        "适用范围：星汇广场全部楼栋商户",
        "第三条 响应时限",
        "3.1 空调类故障报修后，物业应在 24 小时内响应，48 小时内到场检修。",
        "3.2 给排水类故障报修后，物业应在 8 小时内响应，24 小时内到场处理。",
    ),
    (
        "3.3 电梯、消防类故障按重大事件处理，物业应立即响应并同步通报项目负责人。",
        "第四条 记录要求",
        "4.1 每次报修应生成工单，记录报修时间、响应时间、到场时间与处理结果。",
        "4.2 工单闭环前不得关闭，未闭环工单应按周上报。",
    ),
)

_REGISTERED_FONT = "SyntheticContractCN"

#: 探测顺序：Windows → macOS → Linux 常见中文字体。
_CANDIDATE_FONTS: tuple[str, ...] = (
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simkai.ttf",
    r"C:\Windows\Fonts\simfang.ttf",
    r"C:\Windows\Fonts\Deng.ttf",
    "/System/Library/Fonts/Supplemental/Songti.ttf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)


def _first_existing_font() -> str | None:
    for candidate in _CANDIDATE_FONTS:
        # reportlab 的 TTFont 不支持 TTC 字体集合，只接受单体 TTF/OTF。
        if candidate.lower().endswith(".ttc"):
            continue
        if Path(candidate).is_file():
            return candidate
    return None


def resolve_font_name() -> str:
    """返回可用的中文字体名；有 TTF 就子集嵌入，否则退回 CID 字体。"""

    if _REGISTERED_FONT in pdfmetrics.getRegisteredFontNames():
        return _REGISTERED_FONT

    font_path = _first_existing_font()
    if font_path is not None:
        pdfmetrics.registerFont(TTFont(_REGISTERED_FONT, font_path))
        return _REGISTERED_FONT

    cid_name = "STSong-Light"
    if cid_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(cid_name))
    return cid_name


def build_pdf(
    path: str | Path,
    pages: tuple[tuple[str, ...], ...],
    *,
    title: str,
) -> Path:
    """按页写入中文 PDF，返回路径。页脚不参与条款正文（chunker 会剔除）。"""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    font_name = resolve_font_name()
    canvas = Canvas(str(target), pagesize=A4)
    canvas.setTitle(title)
    canvas.setAuthor("commercial-property-multi-agent")
    canvas.setSubject("synthetic document for offline RAG evaluation")

    page_width, page_height = A4
    for page_index, lines in enumerate(pages):
        canvas.setFont(font_name, 11)
        y = page_height - 72
        for line in lines:
            canvas.drawString(56, y, line)
            y -= 20
        canvas.setFont(font_name, 9)
        canvas.drawRightString(
            page_width - 56, 40, f"第 {page_index + 1} 页 / 共 {len(pages)} 页"
        )
        canvas.showPage()

    canvas.save()

    if target.stat().st_size == 0:  # pragma: no cover - 防御性检查
        raise RuntimeError(f"PDF 生成失败：{target} 为空文件")

    return target


def build_contract_pdf(path: str | Path) -> Path:
    return build_pdf(path, CONTRACT_PAGES, title="租赁合同（合成样本）")


def build_policy_pdf(path: str | Path) -> Path:
    return build_pdf(path, POLICY_PAGES, title="星汇广场物业报修响应标准（合成样本）")


if __name__ == "__main__":  # pragma: no cover - 手动生成入口
    from ..paths import DOCUMENT_DIR

    output_dir = Path(os.environ.get("DOC_OUT_DIR", str(DOCUMENT_DIR)))
    print(build_contract_pdf(output_dir / "lease_xh_a301_contract_v1.pdf"))
    print(build_policy_pdf(output_dir / "property_policy_v1.pdf"))

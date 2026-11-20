"""Pydantic 数据模型。"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, FiniteFloat, model_validator


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str
    version: str


class FcsSummary(BaseModel):
    """单个 FCS 文件的解析摘要。"""

    filename: str
    event_count: int
    channel_count: int
    # 荧光通道标签（如 FITC-A, PE-A），保持文件中的顺序
    channel_labels: list[str]
    # 非荧光参数（如 FSC-A, SSC-A, Time）
    scatter_labels: list[str]
    sample_id: str | None = None
    # 文件是否内嵌 $SPILLOVER 补偿矩阵（有则后端默认应用补偿）
    has_spillover: bool = False
    # 补偿是否实际应用成功（False=无矩阵或矩阵损坏静默降级）
    compensation_applied: bool = False


class FileUploadResponse(BaseModel):
    """FCS 上传成功后的响应。"""

    file_id: str
    summary: FcsSummary


class EventsResponse(BaseModel):
    """散点图事件数据（已下采样）。"""

    x_label: str
    y_label: str
    total_events: int
    sampled: int
    x: list[float]
    y: list[float]
    # 数据空间："comp"=已补偿线性，"raw"=原始未补偿，"logicle"=补偿+logicle 显示
    data_space: Literal["raw", "comp", "logicle"]
    # 文件是否有补偿矩阵（compensate 请求被忽略时置 False）
    compensated: bool = False
    # 文件有 $SPILLOVER 但补偿失败：当前返回的是未补偿数据
    uncompensated_fallback: bool = False


class GateDef(BaseModel):
    """一个门控定义（矩形或多边形，二维）。"""

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[\w\u4e00-\u9fff _\-\(\)]{1,64}$",
        description="门名：仅允许中文/字母/数字/下划线/空格/连字符/圆括号",
    )
    type: Literal["rect", "polygon"]
    x_label: str = Field(min_length=1, max_length=256)
    y_label: str = Field(min_length=1, max_length=256)
    # 矩形门：两维各自的范围
    x_min: FiniteFloat | None = None
    x_max: FiniteFloat | None = None
    y_min: FiniteFloat | None = None
    y_max: FiniteFloat | None = None
    # 多边形门：顶点坐标 [[x, y], ...]
    vertices: list[Annotated[list[FiniteFloat], Field(min_length=2, max_length=2)]] = Field(default_factory=list, max_length=10000)
    parent_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def valid_geometry(self) -> Self:
        if self.type == "rect":
            if any(v is None for v in (self.x_min, self.x_max, self.y_min, self.y_max)):
                raise ValueError("矩形门缺少范围")
            if self.x_min >= self.x_max or self.y_min >= self.y_max:
                raise ValueError("矩形门下界必须小于上界")
        elif len(self.vertices) < 3:
            raise ValueError("多边形门至少需要 3 个二维顶点")
        return self


class GateEvaluation(BaseModel):
    """单个门的评估统计。"""

    id: str
    name: str
    event_count: int
    absolute_percent: float
    relative_percent: float
    # 文件有 $SPILLOVER 但补偿失败：统计基于未补偿数据
    uncompensated_fallback: bool = False


class GatesPayload(BaseModel):
    """保存的门控树。"""

    gates: list[GateDef] = Field(max_length=1000)

    @model_validator(mode="after")
    def valid_tree(self) -> Self:
        parents = {gate.id: gate.parent_id for gate in self.gates}
        if len(parents) != len(self.gates):
            raise ValueError("门 id 必须唯一")
        for gate in self.gates:
            current: str | None = gate.id
            seen: set[str] = set()
            while current is not None:
                if current not in parents:
                    raise ValueError("门的父节点不存在")
                if current in seen:
                    raise ValueError("门控树不能有环")
                seen.add(current)
                if len(seen) > 64:
                    raise ValueError("门控层级不能超过 64 层")
                current = parents[current]
        return self


class ApiError(BaseModel):
    """统一错误响应。"""

    detail: str

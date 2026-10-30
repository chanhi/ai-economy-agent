from typing import Literal
from pydantic import BaseModel, Field


class HourlyFilterSchema(BaseModel):
    selected_indices: list[int] = Field(
        default_factory=list,
        description="선별된 기사의 0-based 정수 인덱스 번호 리스트",
    )


class DeskSchema(BaseModel):
    today_keyword: str = Field(description="오늘 시장을 관통하는 핵심 키워드 1개 (특수문자 제외)")
    market_overview: str = Field(description="전체 거시 경제 흐름과 시장 관전 포인트 2~3문장 (옵시디언 [[백링크]] 포함)")
    sentiment_score: int = Field(
        default=50,
        ge=0,
        le=100,
        description="시장 공포/탐욕 지수 (0=극단적 공포, 50=중립, 100=극단적 탐욕)",
    )
    sentiment_label: str = Field(
        default="중립",
        description="투심 상태 라벨 (극단적 공포 / 공포 / 경계 / 중립 / 낙관 / 탐욕 / 극단적 탐욕 중 택1)",
    )
    selected_ids: list[str] = Field(
        default_factory=list,
        description="중복 없이 선별된 핵심 기사 ID 문자열 리스트",
    )


class TermItemSchema(BaseModel):
    term: str = Field(description="금융/경제 전문 용어명")
    explanation: str = Field(description="초보자도 이해하기 쉬운 비유 기반 1~2문장 설명 ([[백링크]] 포함 가능)")


class AnalystSchema(BaseModel):
    id: str = Field(description="분석 대상 기사 고유 ID")
    selection_reason: str = Field(description="이 기사를 핵심 리포트로 선정한 이유 1문장 ([[백링크]] 적용)")
    thinking_process: str = Field(description="최근 시장 흐름 및 과거 유사 선례와 비교한 추세 지속/변곡점 추론")
    summary: list[str] = Field(
        description="반드시 4개 항목: 📌 **[핵심 팩트]**: ..., 🔍 **[배경/원인]**: ..., 📊 **[영향/수치]**: ..., 🎯 **[향후 전망]**: ... (모두 [[백링크]] 적용)"
    )
    affected_sectors: list[str] = Field(description="호재/악재를 받는 구체적 섹터 목록 (예: '[[반도체]](호재)')")
    terms: list[TermItemSchema] = Field(default_factory=list, description="기사 내 핵심 금융/경제 용어 1~2개 해설")


class EditorSynthesisSchema(BaseModel):
    market_phase: Literal["Bull", "Bear", "Sideways"] = Field(
        description="현재 시장 국면 (Bull / Bear / Sideways 중 1개)"
    )
    editor_summary: str = Field(
        description="데스크 시황과 전체 심층 분석 데이터를 아우르는 3~4문장 수석 센터장 통찰 요약 (주요 명사에 [[백링크]] 필수 적용)"
    )
    macro_commentary: list[str] = Field(
        description="각 거시 지표별 수치와 시장 함의를 설명하는 불릿 문장 리스트 (예: '**S&P 500**: 7,720.39 (+0.60%) 기록. [[연준]]의 ...')"
    )


class ReviewerSchema(BaseModel):
    passed: bool = Field(description="리포트 품질 기준 통과 여부")
    feedback: str = Field(description="반려 시 구체적인 수정 지시사항, 통과 시 '완벽합니다'")


class RagAnswerSchema(BaseModel):
    answer: str = Field(description="검색된 과거 리포트 근거에 기반한 명확하고 전문적인 한국어 답변 (3~6문장)")
    key_points: list[str] = Field(default_factory=list, description="핵심 요약 포인트 2~3개")

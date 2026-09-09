// 백엔드 API 응답 타입 (coding-standards.md: 컴포넌트 안에서 인라인으로 만들지 않는다)

export type RiskLevel = "SAFE" | "CAUTION" | "DANGER";
export type AtmAction = "ALLOW" | "VERIFY" | "BLOCK";
export type AtmStatus =
  | "READY"
  | "WITHDRAW_ENABLED"
  | "WITHDRAW_BLOCKED"
  | "CALL_CENTER";
export type CallcenterResolution = "MAINTAINED" | "RELEASED";

/** 성공 응답은 항상 data로 감싸여 온다 (api-rules.md) */
export interface ApiEnvelope<T> {
  data: T;
}

export interface ApiErrorBody {
  error: { code: string; message: string };
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: number;
  username: string;
  display_name: string;
  /** "user" = 일반 사용자, "agent" = 콜센터 상담원 (backend/db/models.py) */
  role: "user" | "agent";
}

export interface ChatRoomResponse {
  id: number;
  title: string;
  last_message: string | null;
  last_message_at: string | null;
}

export interface MessageResponse {
  id: number;
  chat_room_id: number;
  sender_label: string;
  content: string;
  sent_at: string;
}

export interface AnalysisResponse {
  analysis_id: number;
  risk_level: RiskLevel;
  risk_score: number;
  reasons: string[];
  summary: string;
  detected_at: string;
  message_text: string;
  session_id: string | null;
  atm_action: AtmAction;
}

export interface AtmSessionResponse {
  session_id: string;
  risk_level: RiskLevel;
  risk_score: number;
  atm_status: AtmStatus;
}

export interface CallcenterSessionResponse {
  session_id: string;
  analysis_id: number;
  user_display_name: string;
  risk_level: RiskLevel;
  risk_score: number;
  reasons: string[];
  message_text: string;
  atm_status: AtmStatus;
  callcenter_resolution: CallcenterResolution | null;
  detected_at: string;
  scanned_at: string | null;
  resolved_at: string | null;
}

/** 라즈베리파이 로컬 데몬(/state)이 돌려주는 ATM 화면 상태 */
export interface AtmDaemonState {
  state: AtmStatus;
  session_id: string | null;
  risk_level: RiskLevel | null;
  risk_score: number | null;
  reasons: string[];
  summary: string;
  guidance: string;
  can_withdraw: boolean;
  /** 상담원이 이미 확인을 끝냈으면 그 결과 (확인 전에는 null) */
  callcenter_resolution: CallcenterResolution | null;
  last_error: string | null;
  /** 부스를 운영하는 사람이 고칠 수 있게 원인을 짚어 주는 한 줄 (평소에는 null) */
  operator_hint: string | null;
  offline: boolean;
}

/** WebSocket으로 오는 실시간 이벤트 */
export type SocketEvent =
  | {
      type: "atm_scan";
      session_id: string;
      risk_level: RiskLevel;
      risk_score: number;
      atm_status: AtmStatus;
    }
  | {
      type: "withdraw_attempt";
      session_id: string;
      dispensed: boolean;
      atm_status: AtmStatus;
      risk_level: RiskLevel;
    }
  | {
      type: "callcenter_resolved";
      session_id: string;
      callcenter_resolution: CallcenterResolution;
      atm_status: AtmStatus;
    };

// Google Identity Services – ambient TypeScript declarations
// Mirrors the subset of the GSI API used in this project.

interface GoogleCredentialResponse {
  credential: string          // The JWT ID-token
  select_by: string
  clientId?: string
}

interface GsiButtonConfig {
  type?: 'standard' | 'icon'
  theme?: 'outline' | 'filled_blue' | 'filled_black'
  size?: 'large' | 'medium' | 'small'
  text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin'
  shape?: 'rectangular' | 'pill' | 'circle' | 'square'
  logo_alignment?: 'left' | 'center'
  width?: string | number
  locale?: string
}

interface GsiIdConfig {
  client_id: string
  callback: (response: GoogleCredentialResponse) => void
  auto_select?: boolean
  cancel_on_tap_outside?: boolean
  context?: 'signin' | 'signup' | 'use'
  ux_mode?: 'popup' | 'redirect'
  login_uri?: string
  nonce?: string
  hosted_domain?: string
}

interface GsiAccounts {
  id: {
    initialize(config: GsiIdConfig): void
    prompt(momentListener?: (notification: PromptMomentNotification) => void): void
    renderButton(parent: HTMLElement, options: GsiButtonConfig): void
    disableAutoSelect(): void
    storeCredential(credential: { id: string; password: string }, callback?: () => void): void
    cancel(): void
    revoke(hint: string, callback: (done: RevokeDoneResponse) => void): void
  }
}

interface PromptMomentNotification {
  isDisplayMoment(): boolean
  isDisplayed(): boolean
  isNotDisplayed(): boolean
  getNotDisplayedReason(): string
  isSkippedMoment(): boolean
  getSkippedReason(): string
  isDismissedMoment(): boolean
  getDismissedReason(): string
  getMomentType(): string
}

interface RevokeDoneResponse {
  successful: boolean
  error?: string
}

declare global {
  interface Window {
    google?: {
      accounts: GsiAccounts
    }
  }
}

export {}

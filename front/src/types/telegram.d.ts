interface TelegramUser {
  id: number
  name: string
  preferred_username?: string
  picture?: string
  phone_number?: string
}

interface TelegramLoginResponse {
  id_token?: string
  user?: TelegramUser
  error?: string
}

interface TelegramLoginInitOptions {
  client_id: number
  request_access?: ('phone' | 'write')[]
  lang?: string
  nonce?: string
}

interface TelegramLogin {
  init(options: TelegramLoginInitOptions, callback: (response: TelegramLoginResponse) => void): void
  open(callback?: (response: TelegramLoginResponse) => void): void
  auth(options: TelegramLoginInitOptions, callback: (response: TelegramLoginResponse) => void): void
}

declare global {
  interface Window {
    Telegram?: {
      Login: TelegramLogin
    }
  }
}

export {}

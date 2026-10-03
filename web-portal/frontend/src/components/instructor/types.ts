export type Tab = 'overview' | 'announcement' | 'labs' | 'students'

export type Announcement = { 
  id: number
  message: string
  date: string
  published: boolean 
}

export type Course = { 
  code: string
  name: string
  lecturer_name: string
  image_url: string
  background_key: string
  icon_key: string
}

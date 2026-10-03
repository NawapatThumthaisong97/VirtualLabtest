export type Tab = 'overview' | 'announcement' | 'labs' | 'students'

export type Announcement = { 
  id: string
  message: string
  createdAt: string
  authorName: string
}

export type Course = { 
  id: string
  code: string
  name: string
  lecturer_name: string
  image_url: string | null
  background_key: string | null
  icon_key: string | null
  announcements?: Announcement[]
}

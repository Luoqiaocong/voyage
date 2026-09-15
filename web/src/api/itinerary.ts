import http from './http'

export interface ItineraryActivity {
  time_slot: 'morning' | 'afternoon' | 'evening'
  kind: 'attraction' | 'restaurant' | 'hotel' | 'transport' | 'rest'
  name: string
  description: string
  duration_hours: number
  cost: number
  note?: string | null
}

export interface ItineraryDay {
  day_no: number
  date?: string | null
  theme: string
  activities: ItineraryActivity[]
  summary: string
}

export interface ItineraryPlan {
  destination: string
  days: number
  budget?: number | null
  preferences: string[]
  transport?: string | null
  accommodation?: ItineraryActivity | null
  daily_plans: ItineraryDay[]
  tips: string[]
}

export interface ItineraryDetail {
  id: number
  conversation_id: string | null
  plan: ItineraryPlan
  created_at: string
  updated_at: string
}

export interface ItineraryPatch {
  budget?: number | null
  preferences?: string[]
  transport?: string | null
  tips?: string[]
  accommodation?: ItineraryActivity | null
}

export async function listItineraries(): Promise<ItineraryDetail[]> {
  const data = (await http.get('/itineraries/')) as unknown as { itineraries?: ItineraryDetail[] }
  return data.itineraries ?? []
}

export async function getItinerary(id: number): Promise<ItineraryDetail> {
  return (await http.get(`/itineraries/${id}`)) as unknown as ItineraryDetail
}

export async function extractItinerary(conversationId: string): Promise<ItineraryDetail> {
  return (await http.post(`/itineraries/extract/${conversationId}`)) as unknown as ItineraryDetail
}

export async function updateItinerary(id: number, plan: ItineraryPlan): Promise<ItineraryDetail> {
  return http.put(`/itineraries/${id}`, plan)
}

export async function patchItinerary(id: number, patch: ItineraryPatch): Promise<ItineraryDetail> {
  return http.patch(`/itineraries/${id}`, patch)
}

export async function deleteItinerary(id: number): Promise<void> {
  await http.delete(`/itineraries/${id}`)
}

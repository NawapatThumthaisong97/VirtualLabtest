/**
 * Toast Demo Page - สำหรับทดสอบ Toast Component
 */
import { useToast } from '../hooks/useToast'

export default function ToastDemo() {
  const toast = useToast()

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="mx-auto max-w-2xl">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Toast Notification Demo</h1>
        <p className="text-slate-600 mb-8">Click buttons to test different toast types</p>
        
        <div className="grid gap-4 sm:grid-cols-2">
          <button
            onClick={() => toast.success('Success!', 'Your action completed successfully.')}
            className="h-24 rounded-xl bg-emerald-600 text-white font-semibold hover:bg-emerald-700 transition"
          >
            ✅ Show Success Toast
          </button>
          
          <button
            onClick={() => toast.error('Error!', 'Something went wrong. Please try again.')}
            className="h-24 rounded-xl bg-red-600 text-white font-semibold hover:bg-red-700 transition"
          >
            ❌ Show Error Toast
          </button>
          
          <button
            onClick={() => toast.info('Information', 'Here is some useful information for you.')}
            className="h-24 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 transition"
          >
            ℹ️ Show Info Toast
          </button>
          
          <button
            onClick={() => toast.warning('Warning!', 'Please be careful with this action.')}
            className="h-24 rounded-xl bg-amber-600 text-white font-semibold hover:bg-amber-700 transition"
          >
            ⚠️ Show Warning Toast
          </button>
        </div>

        <div className="mt-8 p-6 bg-white rounded-xl border border-slate-200">
          <h2 className="font-bold text-slate-900 mb-3">Usage Example:</h2>
          <pre className="text-sm text-slate-700 bg-slate-50 p-4 rounded-lg overflow-x-auto">
{`import { useToast } from '../hooks/useToast'

function MyComponent() {
  const toast = useToast()

  const handleSave = async () => {
    try {
      await saveData()
      toast.success('Saved!', 'Your data has been saved.')
    } catch (error) {
      toast.error('Failed!', 'Unable to save data.')
    }
  }

  return <button onClick={handleSave}>Save</button>
}`}
          </pre>
        </div>
      </div>
    </div>
  )
}

import { RouterProvider } from 'react-router-dom';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import router from './routes';
import ToastContainer from './components/ToastContainer';
import { useToastStore } from './hooks/useToast';

// Create a client for React Query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      gcTime: 1000 * 60 * 10, // 10 minutes (formerly cacheTime)
      refetchOnWindowFocus: false, // ปิด refetch ตอน focus window (สำหรับ dev)
      refetchOnMount: false, // ปิด refetch ตอน component mount ถ้ายังมี cache
    },
  },
});

function App() {
  const { toasts, removeToast } = useToastStore()
  
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <ToastContainer toasts={toasts} onClose={removeToast} />
    </QueryClientProvider>
  );
}

export default App;

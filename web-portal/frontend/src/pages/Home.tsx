/**
 * Home Page
 */
import { useQuery } from '@tanstack/react-query';
import { exampleService } from '../services/example';

export default function HomePage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['examples'],
    queryFn: () => exampleService.getAll(),
  });

  if (isLoading) return <div className="max-w-7xl mx-auto px-4 py-12">Loading...</div>;
  if (error) return <div className="max-w-7xl mx-auto px-4 py-12 text-red-500">Error: {String(error)}</div>;

  return (
    <div className="max-w-7xl mx-auto px-4 py-12">
      <h1 className="text-4xl font-bold mb-2">Home</h1>
      <p className="text-gray-600 mb-8">Total Examples: {data?.length || 0}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {data?.map((item) => (
          <div key={item.id} className="p-6 border rounded-lg shadow hover:shadow-lg transition">
            <h2 className="text-xl font-semibold mb-2">{item.title}</h2>
            <p className="text-gray-600 mb-4">{item.description}</p>
            <p className="text-sm text-gray-400">
              {new Date(item.created_at).toLocaleDateString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

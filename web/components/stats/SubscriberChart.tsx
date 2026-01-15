'use client';

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface SubscriberChartProps {
  distribution: {
    tiny: number;
    small: number;
    medium: number;
    large: number;
    mega: number;
  };
}

export default function SubscriberChart({ distribution }: SubscriberChartProps) {
  const data = [
    { name: '<1k', count: distribution.tiny, label: 'Tiny' },
    { name: '1k-10k', count: distribution.small, label: 'Small' },
    { name: '10k-100k', count: distribution.medium, label: 'Medium' },
    { name: '100k-1M', count: distribution.large, label: 'Large' },
    { name: '1M+', count: distribution.mega, label: 'Mega' },
  ];

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey="name" stroke="#9CA3AF" />
        <YAxis stroke="#9CA3AF" />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1F2937',
            border: '1px solid #4B5563',
            borderRadius: '8px',
            color: '#F3F4F6',
          }}
        />
        <Bar dataKey="count" fill="#A855F7" radius={[8, 8, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

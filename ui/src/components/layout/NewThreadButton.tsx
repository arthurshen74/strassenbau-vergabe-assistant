import { useNavigate } from 'react-router-dom';
import { Button } from '../ui/button';
import { PlusIcon } from '@heroicons/react/16/solid';

export function NewThreadButton() {
  const navigate = useNavigate();
  return (
    <Button
      onClick={() => navigate('/c/new')}
      className="w-full justify-center"
    >
      <PlusIcon />
      New thread
    </Button>
  );
}

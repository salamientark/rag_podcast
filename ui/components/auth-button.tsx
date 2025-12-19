'use client';

import { useRouter } from 'next/navigation';
import { signOut, useSession } from 'next-auth/react';
import { Button } from '@/components/ui/button';
import { toast } from './toast';
import { guestRegex } from '@/lib/constants';

export function AuthButton() {
  const router = useRouter();
  const { data, status } = useSession();

  const isGuest = guestRegex.test(data?.user?.email ?? '');
  const canLogin = isGuest || !data?.user?.email

  const handleAuthAction = () => {
    if (status === 'loading') {
      toast({
        type: 'error',
        description: 'Checking authentication status, please try again!',
      });
      return;
    }

    if (canLogin) {
      router.push('/login');
    } else {
      signOut({
        redirectTo: '/',
      });
    }
  };

  return (
    <Button
      variant={canLogin ? 'default' : 'outline'}
      size="sm"
      onClick={handleAuthAction}
      disabled={status === 'loading'}
      className={canLogin ? 'dark:bg-white dark:text-black dark:hover:bg-white/90' : ''}
    >
      {canLogin ? 'Login' : 'Sign out'}
    </Button>
  );
}

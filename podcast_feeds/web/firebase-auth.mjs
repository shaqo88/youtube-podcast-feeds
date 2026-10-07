import { initializeApp } from 'firebase/app';
import { getAuth,GoogleAuthProvider,signInWithPopup,onAuthStateChanged,signOut,reauthenticateWithPopup } from 'firebase/auth';

export function createAuth(config) {
  const auth=getAuth(initializeApp(config));
  const provider=new GoogleAuthProvider();
  provider.setCustomParameters({prompt:'select_account'});
  return { subscribe:callback=>onAuthStateChanged(auth,callback),
    signIn:()=>signInWithPopup(auth,provider),signOut:()=>signOut(auth),
    reauthenticate:()=>reauthenticateWithPopup(auth.currentUser,provider),
    token:(force,uid)=>auth.currentUser?.uid===uid?auth.currentUser.getIdToken(force):Promise.reject(new Error('account_changed')),current:()=>auth.currentUser };
}

// =====================================================================
// Connexion à Supabase, partagée par toutes les pages du site.
//
// Ces deux valeurs peuvent être publiques : la clé « publishable » ne permet
// que ce que les règles d'accès de Supabase autorisent.
// ⚠️ Ne mets JAMAIS la clé secrète (sb_secret_…) ici.
// =====================================================================
const SUPABASE_URL = "https://avptzjzildtgelzyhubz.supabase.co";      // ← l'adresse de ton projet
const SUPABASE_CLE_PUBLIQUE = "sb_publishable_JI1hNvagrnHLQxmTwcuqKw_NidnxbVn";       // ← ta clé publique

// Les comptes n'ont pas d'e-mail. Supabase en demande un, donc on le fabrique à partir du pseudo.
// « .invalid » est un domaine réservé qui n'existe pas : aucun e-mail ne peut partir vers quelqu'un.
const DOMAINE_COMPTES = "platine.invalid";
const FORMAT_PSEUDO = /^[A-Za-z0-9_-]{3,20}$/;
const MOT_DE_PASSE_MINIMUM = 8;

if (SUPABASE_CLE_PUBLIQUE.startsWith("sb_secret_")) {
  throw new Error("compte.js contient la clé SECRÈTE : remplace-la par la clé publique (sb_publishable_…) et change la clé secrète dans Supabase.");
}

const supa = supabase.createClient(SUPABASE_URL, SUPABASE_CLE_PUBLIQUE);

// « Antoine » -> « antoine@platine.invalid »
function adressePour(pseudo) {
  return `${pseudo.trim().toLowerCase()}@${DOMAINE_COMPTES}`;
}

async function seConnecter(pseudo, motDePasse) {
  const { error } = await supa.auth.signInWithPassword({ email: adressePour(pseudo), password: motDePasse });
  if (error) throw error;
}

async function creerCompte(pseudo, motDePasse) {
  const { data, error } = await supa.auth.signUp({
    email: adressePour(pseudo),
    password: motDePasse,
    options: { data: { pseudo: pseudo.trim() } },   // lu par la base pour créer le profil
  });
  if (error) throw error;
  if (!data.session) {
    throw new Error("Compte créé, mais Supabase attend une confirmation par e-mail : désactive « Confirm email » dans Supabase, puis connecte-toi.");
  }
}

async function seDeconnecter() {
  await supa.auth.signOut();
}

// Renvoie { id, pseudo } si quelqu'un est connecté, sinon null
async function joueurConnecte() {
  const { data: { session } } = await supa.auth.getSession();
  if (!session) return null;
  const { data: profil } = await supa.from("profils").select("pseudo").maybeSingle();
  return { id: session.user.id, pseudo: profil?.pseudo ?? session.user.user_metadata?.pseudo ?? "?" };
}

// Traduit les erreurs de Supabase en phrases claires
function messageErreur(erreur) {
  const code = erreur?.code || "";
  const texte = erreur?.message || String(erreur);
  if (code === "invalid_credentials") return "Pseudo ou mot de passe incorrect.";
  if (code === "user_already_exists" || code === "email_exists") return "Ce pseudo est déjà pris.";
  if (code === "weak_password") return `Mot de passe trop faible : au moins ${MOT_DE_PASSE_MINIMUM} caractères.`;
  if (code.startsWith("over_")) return "Trop d'essais : réessaie dans quelques minutes.";
  if (code === "email_not_confirmed") return "Compte pas encore confirmé : désactive « Confirm email » dans Supabase.";
  if (code === "signup_disabled") return "Les inscriptions sont fermées pour le moment.";
  if (texte.includes("Database error saving new user")) return "Inscription refusée par la base : pseudo invalide ou déjà pris.";
  if (texte.includes("Invalid API key")) return "La clé publique dans compte.js n'est pas la bonne.";
  if (texte.includes("Failed to fetch") || texte.includes("NetworkError")) return "Impossible de joindre Supabase : vérifie l'adresse dans compte.js et ta connexion.";
  return texte;
}
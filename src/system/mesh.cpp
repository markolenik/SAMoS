/* *************************************************************
 *  
 *   Soft Active Mater on Surfaces (SAMoS)
 *   
 *   Author: Rastko Sknepnek
 *  
 *   Division of Physics
 *   School of Engineering, Physics and Mathematics
 *   University of Dundee
 *   
 *   (c) 2013, 2014
 * 
 *   School of Science and Engineering
 *   School of Life Sciences 
 *   University of Dundee
 * 
 *   (c) 2015
 * 
 *   Author: Silke Henkes
 * 
 *   Department of Physics 
 *   Institute for Complex Systems and Mathematical Biology
 *   University of Aberdeen  
 * 
 *   (c) 2014, 2015
 *  
 *   This program cannot be used, copied, or modified without
 *   explicit written permission of the authors.
 * 
 * ************************************************************* */

/*!
 * \file mesh.cpp
 * \author Rastko Sknepnek, sknepnek@gmail.com
 * \date 18-Nov-2015
 * \brief Implementation of Mesh class memebr functions
 */ 

#include "mesh.hpp"

/*! Checks if an element is in the vector
 *  \param v vector of numbers
 *  \param e element we are looking for
 */
static bool in(vector<int>& v, int e)
{
  if (find(v.begin(),v.end(),e) == v.end())
    return false;
  return true;
}

// Class members defined below

/*! Clean up the entire mesh data structure. */
void Mesh::reset()
{
  m_size = 0;  m_nedge = 0;  m_nface = 0;
  m_vertices.clear();           
  m_edges.clear();              
  m_faces.clear();              
  m_edge_map.clear();  
}

/*! Add and edge to the list of edges. Edge is defined
 *  by the indices of two vertices that belong to it.
 *  We also populate the auxiliary data structure edge_map
 *  that allows us to quickly search over vertex pairs.
 *  \param ei index of the 1st vertex
 *  \param ej index of the 2nd vertex
*/
void Mesh::add_edge(int ei, int ej)
{
  m_edges.push_back(Edge(m_nedge,ei,ej));
  m_vertices[ei].add_edge(m_nedge);
  m_vertices[ej].add_edge(m_nedge);
  m_vertices[ei].add_neighbour(ej);
  m_vertices[ej].add_neighbour(ei);
  m_edge_map[make_pair(ei,ej)] = m_nedge;
  m_edge_map[make_pair(ej,ei)] = m_nedge;
  m_nedge++;
}

/*! Add a face to the list of all faces. Face is 
 *  defined by specifying list (vector) of vertices
 *  that define it.
 *  \param lv list of vertices
*/
void Mesh::add_face(vector<int>& lv)
{
  m_faces.push_back(Face(m_nface));
  int N = lv.size();
  for (int i = 0; i < N; i++)
    m_faces[m_nface].add_vertex(lv[i]);
  for (int i = 0; i < N; i++)
  {
    m_vertices[lv[i]].faces.push_back(m_nface);
    for (int j = i + 1; j < N; j++)
    {
      VertexPair vp = make_pair(lv[i],lv[j]);
      if (m_edge_map.find(vp) != m_edge_map.end())
      {
        int e = m_edge_map[vp];
        m_faces[m_nface].add_edge(e);
        if (m_edges[e].f1 == NO_FACE) m_edges[e].f1 = m_nface;
        else m_edges[e].f2 = m_nface;
      }
    }
  }
  this->compute_centre(m_nface);
  m_nface++;
}

/*! Once the mesh is read in, we need to set things like
 *  boundary flags and make use that the edge_face data strucutre
 *  has been populated. 
 *
 *  For boundaries we loop over all vertices, edges and faces and set 
 *  boundary flags to true is any of those are at the boundary.
 *  Edge is on boundary if it has only one face.
 *  Vertex is on boundary if at least one of the edges is boundary.
 *  Face is a boundary face if all its edges are boundary edges.
*/ 
void Mesh::postprocess()
{
  for (int i = 0; i < m_nedge; i++)
    if (m_edges[i].f1 == NO_FACE || m_edges[i].f2 == NO_FACE) m_edges[i].boundary = true;
  for (int i = 0; i < m_size; i++)
    for (int j = 0; j < m_vertices[i].edges.size(); j++)
      if (m_edges[m_vertices[i].edges[j]].boundary)  
      { 
        m_vertices[i].boundary = true;   // vertex is a boundary vertex if at least one of its edges is boundary edge
        break;
      }
   for (int i = 0; i < m_nface; i++)
   {
      m_faces[i].edge_face = true;
      for (int j = 0; j < m_faces[i].edges.size(); j++)
        m_faces[i].edge_face = (m_faces[i].edge_face && m_edges[m_faces[i].edges[j]].boundary);
   }
   for (int i = 0; i < m_nedge; i++)
     if (!m_edges[i].boundary)
     {
       m_edge_face[make_pair(m_edges[i].f1,m_edges[i].f2)] = i;
       m_edge_face[make_pair(m_edges[i].f2,m_edges[i].f1)] = i;
     }
   for (int i = 0; i < m_size; i++)
     this->order_neigbours(i);
   for (int i = 0; i < m_size; i++)
     this->order_vertex_faces(i);
   for (int i = 0; i < m_nface; i++)
     this->order_face(i);
}

/*! Computes geometric centre of a face. Coordinates are stored in 
 *  the Face object.
 *  \param id of the face 
*/
void Mesh::compute_centre(int f)
{
  Face& face = m_faces[f];
  double xc = 0.0, yc = 0.0, zc = 0.0;
  for (int i = 0; i < face.n_sides; i++)
  {
    xc += m_vertices[face.vertices[i]].r.x;
    yc += m_vertices[face.vertices[i]].r.y;
    zc += m_vertices[face.vertices[i]].r.z;
  }
  face.rc = Vector3d(xc/face.n_sides,yc/face.n_sides,zc/face.n_sides);
}

/*! This member function orders all neighbours of a vertex.
 *  At this stage it is not possible to determine if the order is
 *  clock or counterclockwise. This will be corrected for later, 
 *  when normals are known. 
 *  \param v vertex whose neighbours to order
 */
void Mesh::order_neigbours(int v)
{
  int N = m_vertices[v].neigh.size();
  // If vertex has only 3 neighbours, they are ordered by defualt
  if (N == 3 && !m_vertices[v].boundary)
    m_vertices[v].ordered_neigh = true;
  else if (N > 3 || m_vertices[v].boundary)
  {
    vector<int> new_neigh;
    new_neigh.push_back(m_vertices[v].neigh[0]);
    while (new_neigh.size() < N)
    {
      int cv = new_neigh[new_neigh.size()-1];
      for (int i = 0; i < N; i++)
      {
        int n = m_vertices[v].neigh[i];
        VertexPair vp = make_pair(cv,n);
        if (m_edge_map.find(vp) != m_edge_map.end() && !in(new_neigh,n))
        {
          new_neigh.push_back(n);
          break;
        }
      }
    }
    copy(new_neigh.begin(), new_neigh.end(), m_vertices[v].neigh.begin());
    // now order edges
    for (int i = 0; i < N; i++)
    {
      VertexPair vp = make_pair(v,m_vertices[v].neigh[i]);
      m_vertices[v].edges[i] = m_edge_map[vp];
    }
    m_vertices[v].ordered_neigh = true;
  }
}


/*! This member function orders all vertice in a face.
 *  At this stage it is not possible to determine if the order is
 *  clock or counterclockwise. This will be corrected for later, 
 *  when normals are known. 
 *  \param f face which we want to order
 */
void Mesh::order_face(int f)
{
  int N = m_faces[f].vertices.size();
  // If the face is a triangle, vertices are ordered by default
  if (N == 3) 
    m_faces[f].ordered = true;
  else if (N > 3 && !m_faces[f].ordered)
  {
    vector<int> new_vert;
    new_vert.push_back(m_faces[f].vertices[0]);
    while (new_vert.size() < N)
    {
      int cv = new_vert[new_vert.size()-1];
      for (int i = 0; i < N; i++)
      {
        int n = m_faces[f].vertices[i];
        VertexPair vp = make_pair(cv,n);
        if (m_edge_map.find(vp) != m_edge_map.end() && !in(new_vert,n))
        {
          new_vert.push_back(n);
          break;
        }
      }
    }
    copy(new_vert.begin(), new_vert.end(), m_faces[f].vertices.begin());
    m_faces[f].ordered = true;
  }
}

/*! Order faces in the vertex star. At this point it is not possible
 *  to determine if the order is clockwise or counterclockwise. This 
 *  will be corrected for once the normal to the vertex is known.
 *  Here we assume that the edges are already ordered, that its that the 
 *  caller has already called order_neigbours(v).
 *  \note In order to avoid complications, at the moment we only oder
 *  faces for non-boundary vertices.
 *  \todo Implement ordering of boundary vertices. 
 *  \param v vertex index
*/
void Mesh::order_vertex_faces(int v)
{
  if (m_vertices[v].ordered_neigh)
  {
    vector<int> new_faces;
    int N = m_vertices[v].edges.size();
    for (int i = 0; i < N-1; i++)
    {
      int e1 = m_vertices[v].edges[i];
      int e2 = m_vertices[v].edges[i+1];
      new_faces.push_back(this->shared_face(e1,e2));
    }
    if (!m_vertices[v].boundary)
    {
      int e1 = m_vertices[v].edges[N-1];
      int e2 = m_vertices[v].edges[0];
      new_faces.push_back(shared_face(e1,e2));
    }
    copy(new_faces.begin(), new_faces.end(),m_vertices[v].faces.begin());
    m_vertices[v].ordered_faces = true;
  }
}

/*! Compute dual area by using expression 
 *  \f$ A_i = \frac{1}{2}\sum_{\mu}\left(\vec r_\mu\times\vec r_{\mu+1}\right)\cdot\vec n_i \f$
 *  were \f$ \vec r_\mu \f$ is the coodinate of the cetre of face \f$ \mu \f$ and \f$ \vec n_i \f$ 
 *  is the normal vector to the vertex.
 *  \note We assume that faces are ordered, otherwise the result will be 
 *  wrong.
 *  \param v verex index
 *  \param n normal vector
*/
double Mesh::dual_area(int v, Vector3d& n)
{
  if (!m_vertices[v].ordered_faces)
    throw runtime_error("Faces need to be ordered before dual area can be computed.");
  Vertex& V = m_vertices[v];
  V.area = 0.0;
  int N = V.faces.size();
  Vector3d nn = n.unit();
  for (int i = 0; i < N-1; i++)
  {
    Vector3d& r1 = m_faces[V.faces[i]].rc;
    Vector3d& r2 = m_faces[V.faces[i+1]].rc;
    Vector3d  rr = cross(r1,r2); 
    V.area += dot(rr,nn);
  }
  // handle the last pair
  Vector3d& r1 = m_faces[V.faces[N-1]].rc;
  Vector3d& r2 = m_faces[V.faces[0]].rc;
  Vector3d  rr = cross(r1,r2); 
  V.area += dot(rr,nn);
  if (area < 0.0)
  {
    area = -area;
    reverse(V.neigh.begin(),V.neigh.end());
    reverse(V.edges.begin(),V.edges.end());
    reverse(V.faces.begin(),V.faces.end());
  }
  V.area = 0.5*area;
  return V.area;
}

/*! Compute lenght of duals perimeter
 *  \f$ l_i = \sum_{\mu}\left|\vec r_\mu-\vec r_{\mu+1}\right| \f$
 *  were \f$ \vec r_\mu \f$ is the coodinate of the cetre of face \f$ \mu \f$.
 *  \note We assume that faces are ordered, otherwise the result will be 
 *  wrong.
 *  \param v verex index
*/
double Mesh::dual_perimeter(int v)
{
  if (!m_vertices[v].ordered_faces)
    throw runtime_error("Faces need to be ordered before dual premeter can be computed.");
  Vertex& V = m_vertices[v];
  V.perim  = 0.0;
  int N = V.faces.size();
  for (int i = 0; i < N-1; i++)
  {
    Vector3d& r1 = m_faces[V.faces[i]].rc;
    Vector3d& r2 = m_faces[V.faces[i+1]].rc;
    V.perim += (r1-r2).len();
  }
  // handle the last pair
  Vector3d& r1 = m_faces[V.faces[N-1]].rc;
  Vector3d& r2 = m_faces[V.faces[0]].rc;
  Vector3d  rr = cross(r1,r2); 
  V.perim += (r1-r2).len();
  return V.perim;
}

/*! An auxiliary function to find shared face between two edges.
 *  If none is found, return -1.
 *  \param e1 index of 1st edge
 *  \param e2 index of 2nd edge
*/
int Mesh::shared_face(int e1, int e2)
{
   if (m_edges[e1].f1 == m_edges[e2].f1 || m_edges[e1].f1 == m_edges[e2].f2) 
      return m_edges[e1].f1;
  else if (m_edges[e1].f2 == m_edges[e2].f1 || m_edges[e1].f2 == m_edges[e2].f2)
      return m_edges[e1].f2;
  else
      return -1;
   
}